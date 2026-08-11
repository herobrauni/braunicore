# Braunicore Ansible

This is a small Ansible control project whose inventory comes from the current
My Idlers API. It does not commit host lists, addresses, API credentials, or
other per-machine secrets.

## Inventory behavior

The executable inventory queries:

```text
https://idlers2.brauni.dev/api/servers
```

It sends the credential only as an `Authorization: Bearer` header, requires
HTTPS and valid certificate verification, refuses redirects, limits response
size, and never includes the token in inventory output or error messages.

Every returned server is placed in `idlers`. Active and inactive records are
split into `idlers_active` and `idlers_inactive`; the included example playbook
targets only `idlers_active`. Additional groups are derived from provider,
location, OS, server type, and labels. Pricing and unrelated Idlers fields are
discarded.

The hostname is the inventory name and default SSH address. `ssh` from Idlers
becomes `ansible_port`, falling back to port 22. Set `IDLERS_ADDRESS_MODE` to
`ipv4` or `ipv6` to prefer the first active address of that family, with the
hostname retained as a fallback.

## One-time setup

The API token previously pasted into chat must be revoked and replaced. Do not
send the replacement through chat or put it in Git. Store it locally:

```bash
install -d -m 0700 ~/.config/braunicore
install -m 0600 /dev/null ~/.config/braunicore/idlers-token
${EDITOR:-vi} ~/.config/braunicore/idlers-token
```

The file must contain only the replacement token. The inventory rejects it if
group or other users can read it. The default path requires no environment
variable; alternatively set `IDLERS_API_TOKEN_FILE` to another mode-0600 file.
`IDLERS_API_TOKEN` is supported for ephemeral CI use but is less convenient for
interactive shells.

Install the pinned controller dependencies:

```bash
cd ansible
uv sync
```

## Inspecting inventory safely

These commands only query Idlers and do not connect to any server:

```bash
uv run ansible-inventory --graph
uv run ansible-inventory --list
uv run ansible-inventory --host example.brauni.dev
```

Optional settings:

```bash
export IDLERS_API_URL=https://idlers2.brauni.dev/api/servers
export IDLERS_API_TIMEOUT=10
export IDLERS_ADDRESS_MODE=hostname  # hostname, ipv4, or ipv6
export IDLERS_ANSIBLE_USER=brauni    # omit when users differ by host
export IDLERS_CA_BUNDLE=/path/to/private-ca.pem
```

Use static `host_vars` or `group_vars` later for per-host SSH users and other
configuration that Idlers does not model. Keep secret values in an encrypted
secret store, not inventory output.

## First connection test

Inventory inspection is read-only. The following command contacts every active
server, so limit it to one disposable/test host first:

```bash
uv run ansible-playbook playbooks/ping.yaml --limit example.brauni.dev
```

Host-key checking is enabled. Populate `known_hosts` through a trusted channel
before connecting; do not disable verification fleet-wide.

## Local validation

The inventory parser and security behavior have offline tests that require no
API token and contact no server:

```bash
uv run -m unittest discover -s tests -v
uv run ansible-playbook -i localhost, playbooks/ping.yaml --syntax-check
```
