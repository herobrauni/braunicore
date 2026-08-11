from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1] / "inventory" / "idlers_inventory.py"
)
SPEC = importlib.util.spec_from_file_location("idlers_inventory", MODULE_PATH)
assert SPEC and SPEC.loader
INVENTORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INVENTORY)


SERVERS = [
    {
        "id": "server01",
        "hostname": "Alpha.Example.com.",
        "active": 1,
        "ssh": 2222,
        "server_type": 1,
        "provider": {"name": "Example Provider"},
        "location": {"name": "Frankfurt, DE"},
        "os": {"name": "Fedora CoreOS"},
        "ips": [
            {
                "address": "192.0.2.10",
                "active": 1,
                "is_ipv4": 1,
            },
            {
                "address": "2001:db8::10",
                "active": 1,
                "is_ipv4": 0,
            },
        ],
        "labels": [{"label": "Production"}, {"label": "Web Tier"}],
        "price": {"amount": "5.00"},
    },
    {
        "id": "server02",
        "hostname": "retired.example.com",
        "active": 0,
        "ssh": None,
        "server_type": 3,
        "provider": None,
        "location": None,
        "os": None,
        "ips": [],
        "labels": [],
    },
]


class InventoryTests(unittest.TestCase):
    def test_inventory_groups_and_operational_hostvars(self):
        result = INVENTORY.build_inventory(SERVERS, ansible_user="operator")
        host = result["_meta"]["hostvars"]["alpha.example.com"]

        self.assertEqual(host["ansible_host"], "alpha.example.com")
        self.assertEqual(host["ansible_port"], 2222)
        self.assertEqual(host["ansible_user"], "operator")
        self.assertEqual(host["idlers_provider"], "Example Provider")
        self.assertNotIn("price", json.dumps(result).lower())
        self.assertIn(
            "alpha.example.com",
            result["idlers_active"]["hosts"],
        )
        self.assertIn(
            "retired.example.com",
            result["idlers_inactive"]["hosts"],
        )
        self.assertIn(
            "alpha.example.com",
            result["idlers_label_web_tier"]["hosts"],
        )

    def test_ipv4_and_ipv6_address_modes(self):
        ipv4 = INVENTORY.build_inventory(SERVERS, address_mode="ipv4")
        ipv6 = INVENTORY.build_inventory(SERVERS, address_mode="ipv6")
        self.assertEqual(
            ipv4["_meta"]["hostvars"]["alpha.example.com"]["ansible_host"],
            "192.0.2.10",
        )
        self.assertEqual(
            ipv6["_meta"]["hostvars"]["alpha.example.com"]["ansible_host"],
            "2001:db8::10",
        )

    def test_duplicate_hostname_is_rejected(self):
        with self.assertRaisesRegex(INVENTORY.InventoryError, "duplicate"):
            INVENTORY.build_inventory([SERVERS[0], SERVERS[0]])

    def test_token_file_requires_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_text("replacement-token\n", encoding="utf-8")
            path.chmod(0o600)
            self.assertEqual(
                INVENTORY.read_token({"IDLERS_API_TOKEN_FILE": str(path)}),
                "replacement-token",
            )

            path.chmod(0o644)
            with self.assertRaisesRegex(
                INVENTORY.InventoryError,
                "group or others",
            ):
                INVENTORY.read_token({"IDLERS_API_TOKEN_FILE": str(path)})

    def test_environment_token_and_wrapped_response(self):
        self.assertEqual(
            INVENTORY.read_token({"IDLERS_API_TOKEN": "replacement-token"}),
            "replacement-token",
        )
        self.assertEqual(INVENTORY.unwrap_servers({"data": SERVERS}), SERVERS)

    def test_api_url_must_be_https_without_credentials(self):
        for value in (
            "http://idlers.example/api/servers",
            "https://user:pass@idlers.example/api/servers",
            "https://idlers.example/api/servers?api_token=bad",
        ):
            with self.subTest(value=value):
                with self.assertRaises(INVENTORY.InventoryError):
                    INVENTORY.validate_api_url(value)


if __name__ == "__main__":
    unittest.main()
