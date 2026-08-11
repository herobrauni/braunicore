#!/usr/bin/env python3
"""Build an Ansible inventory from the My Idlers servers API."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import stat
import sys
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)


DEFAULT_API_URL = "https://idlers2.brauni.dev/api/servers"
DEFAULT_TOKEN_FILE = Path("~/.config/braunicore/idlers-token").expanduser()
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
SERVER_TYPES = {
    1: "kvm",
    2: "openvz",
    3: "dedicated",
    4: "lxc",
    5: "semi_dedicated",
    6: "vmware",
    7: "nat",
}


class InventoryError(RuntimeError):
    """A safe, user-facing inventory failure."""


class NoRedirectHandler(HTTPRedirectHandler):
    """Keep the Bearer credential from being forwarded across redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_token(environ: Mapping[str, str] = os.environ) -> str:
    token = environ.get("IDLERS_API_TOKEN", "").strip()
    configured_file = environ.get("IDLERS_API_TOKEN_FILE", "").strip()

    if token and configured_file:
        raise InventoryError(
            "set only one of IDLERS_API_TOKEN or IDLERS_API_TOKEN_FILE"
        )
    if token:
        return token

    token_file = (
        Path(configured_file).expanduser() if configured_file else DEFAULT_TOKEN_FILE
    )
    if not token_file.exists():
        raise InventoryError(
            "no API token found; set IDLERS_API_TOKEN or create "
            f"{token_file} with mode 0600"
        )
    if not token_file.is_file():
        raise InventoryError(f"token path is not a regular file: {token_file}")

    mode = stat.S_IMODE(token_file.stat().st_mode)
    if mode & 0o077:
        raise InventoryError(
            f"token file must not be accessible by group or others: {token_file}"
        )

    value = token_file.read_text(encoding="utf-8").strip()
    if not value:
        raise InventoryError(f"token file is empty: {token_file}")
    return value


def validate_api_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https":
        raise InventoryError("IDLERS_API_URL must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise InventoryError("IDLERS_API_URL must contain a plain HTTPS host")
    if parsed.query or parsed.fragment:
        raise InventoryError("IDLERS_API_URL must not contain a query or fragment")
    return value.rstrip("/")


def fetch_servers(
    token: str,
    api_url: str,
    timeout: float,
    ca_bundle: str | None = None,
) -> list[dict[str, Any]]:
    context = ssl.create_default_context(cafile=ca_bundle or None)
    opener = build_opener(HTTPSHandler(context=context), NoRedirectHandler())
    request = Request(
        validate_api_url(api_url),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "braunicore-ansible-inventory/1",
        },
        method="GET",
    )

    try:
        with opener.open(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                raise InventoryError(
                    f"Idlers returned unexpected content type {content_type!r}"
                )
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        raise InventoryError(
            f"Idlers API returned HTTP {error.code}"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise InventoryError("could not reach the Idlers API") from error

    if len(body) > MAX_RESPONSE_BYTES:
        raise InventoryError("Idlers API response exceeded 10 MiB")

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InventoryError("Idlers API returned invalid JSON") from error

    return unwrap_servers(payload)


def unwrap_servers(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("data", payload.get("servers"))
    if not isinstance(payload, list):
        raise InventoryError("Idlers API response is not a server list")
    if not all(isinstance(server, dict) for server in payload):
        raise InventoryError("Idlers API server list contains a non-object value")
    return payload


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def relation_name(server: Mapping[str, Any], key: str) -> str | None:
    value = server.get(key)
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for field in ("name", "label"):
            candidate = value.get(field)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return None


def server_labels(server: Mapping[str, Any]) -> list[str]:
    labels = server.get("labels", [])
    if not isinstance(labels, list):
        return []
    names = []
    for label in labels:
        if isinstance(label, str) and label.strip():
            names.append(label.strip())
        elif isinstance(label, dict):
            value = label.get("label", label.get("name"))
            if isinstance(value, str) and value.strip():
                names.append(value.strip())
    return sorted(set(names), key=str.casefold)


def server_ips(server: Mapping[str, Any]) -> list[dict[str, Any]]:
    ips = server.get("ips", [])
    if not isinstance(ips, list):
        return []
    return [
        ip
        for ip in ips
        if isinstance(ip, dict)
        and isinstance(ip.get("address"), str)
        and ip["address"].strip()
        and as_bool(ip.get("active", True))
    ]


def choose_address(server: Mapping[str, Any], mode: str) -> str:
    hostname = str(server.get("hostname", "")).strip().rstrip(".").lower()
    if not hostname or any(character.isspace() for character in hostname):
        raise InventoryError("Idlers server has a missing or invalid hostname")
    if mode == "hostname":
        return hostname

    want_ipv4 = mode == "ipv4"
    for ip in server_ips(server):
        is_ipv4 = as_bool(ip.get("is_ipv4", ":" not in ip["address"]))
        if is_ipv4 == want_ipv4:
            return ip["address"].strip()
    return hostname


def ssh_port(server: Mapping[str, Any]) -> int:
    value = server.get("ssh", server.get("ssh_port", 22)) or 22
    try:
        port = int(value)
    except (TypeError, ValueError) as error:
        raise InventoryError("Idlers server has a non-numeric SSH port") from error
    if not 1 <= port <= 65535:
        raise InventoryError("Idlers server has an invalid SSH port")
    return port


def group_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_value).strip("_").lower()
    return slug or "unknown"


def server_type_name(value: Any) -> str:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return "unknown"
    return SERVER_TYPES.get(numeric, f"type_{numeric}")


def build_inventory(
    servers: Sequence[Mapping[str, Any]],
    address_mode: str = "hostname",
    ansible_user: str | None = None,
) -> dict[str, Any]:
    if address_mode not in {"hostname", "ipv4", "ipv6"}:
        raise InventoryError(
            "IDLERS_ADDRESS_MODE must be hostname, ipv4, or ipv6"
        )

    groups: dict[str, set[str]] = {"idlers": set()}
    hostvars: dict[str, dict[str, Any]] = {}

    def add_to_group(group: str, host: str) -> None:
        groups.setdefault(group, set()).add(host)

    for server in servers:
        hostname = str(server.get("hostname", "")).strip().rstrip(".").lower()
        address = choose_address(server, address_mode)
        if hostname in hostvars:
            raise InventoryError(f"duplicate Idlers hostname: {hostname}")

        active = as_bool(server.get("active", True))
        provider = relation_name(server, "provider")
        location = relation_name(server, "location")
        operating_system = relation_name(server, "os")
        labels = server_labels(server)
        type_name = server_type_name(server.get("server_type"))
        addresses = [ip["address"].strip() for ip in server_ips(server)]

        variables: dict[str, Any] = {
            "ansible_host": address,
            "ansible_port": ssh_port(server),
            "idlers_id": server.get("id"),
            "idlers_active": active,
            "idlers_server_type": type_name,
            "idlers_provider": provider,
            "idlers_location": location,
            "idlers_os": operating_system,
            "idlers_ips": addresses,
            "idlers_labels": labels,
        }
        if ansible_user:
            variables["ansible_user"] = ansible_user
        hostvars[hostname] = variables

        add_to_group("idlers", hostname)
        add_to_group("idlers_active" if active else "idlers_inactive", hostname)
        add_to_group(f"idlers_type_{group_slug(type_name)}", hostname)
        for prefix, value in (
            ("provider", provider),
            ("location", location),
            ("os", operating_system),
        ):
            if value:
                add_to_group(f"idlers_{prefix}_{group_slug(value)}", hostname)
        for label in labels:
            add_to_group(f"idlers_label_{group_slug(label)}", hostname)

    inventory: dict[str, Any] = {
        "_meta": {"hostvars": hostvars},
        "all": {"children": sorted(groups)},
    }
    for name, hosts in sorted(groups.items()):
        inventory[name] = {"hosts": sorted(hosts)}
    return inventory


def positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as error:
        raise InventoryError("IDLERS_API_TIMEOUT must be numeric") from error
    if not 0 < timeout <= 60:
        raise InventoryError("IDLERS_API_TIMEOUT must be between 0 and 60 seconds")
    return timeout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--host", metavar="HOST")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        servers = fetch_servers(
            token=read_token(),
            api_url=os.environ.get("IDLERS_API_URL", DEFAULT_API_URL),
            timeout=positive_timeout(
                os.environ.get("IDLERS_API_TIMEOUT", "10")
            ),
            ca_bundle=os.environ.get("IDLERS_CA_BUNDLE") or None,
        )
        inventory = build_inventory(
            servers,
            address_mode=os.environ.get("IDLERS_ADDRESS_MODE", "hostname"),
            ansible_user=os.environ.get("IDLERS_ANSIBLE_USER") or None,
        )
        output = (
            inventory["_meta"]["hostvars"].get(args.host, {})
            if args.host
            else inventory
        )
        json.dump(output, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    except InventoryError as error:
        print(f"Idlers inventory error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
