# braunicore

`ghcr.io/herobrauni/braunicore:stable` is a thin, signed derivative of
[`ucore-minimal:stable`](https://github.com/ublue-os/ucore). It adds one host
package (`fish`), one secret-free Beszel Quadlet, and the trust scope for this
repository. It deliberately inherits uCore's kernel, boot setup, container
runtimes, signing policy, services, and automatic update configuration.

The repository started from the current
[`ublue-os/image-template`](https://github.com/ublue-os/image-template); it does
not copy or fork the uCore build system.

## Update and release architecture

Renovate watches the digest-pinned uCore base, the version-and-digest-pinned
Beszel agent, GitHub Actions, and Cosign. A dependency pull request must pass
native amd64 and arm64 builds, `bootc container lint`, package assertions,
containers/image policy checks, and Quadlet/systemd validation.

On `main`, each architecture is rechunked, pushed to a commit-specific staging
tag, signed, and verified. CI then creates and signs the multi-architecture
commit tag. Only after containers/image successfully enforces that signature
does CI atomically point the UTC `YYYYMMDD` tag and finally `stable` at the same
digest. A failed build or signature therefore cannot replace the working
`stable` image. Commit and dated tags retain previous releases for diagnosis
and rollback.

## Host packages

Edit [`build_files/packages.txt`](build_files/packages.txt), one Fedora package
per line. Adding or removing an RPM is a one-line change. The build uses `dnf5`;
hosts do not use runtime `rpm-ostree install` layering.

The current uCore base was inspected before this image was created. It already
contains tmux, Tailscale, Podman, Moby/Docker, Docker Buildx/Compose, bootc, and
rpm-ostree, so none is reinstalled. CI continues to assert those critical
packages are present.

## Beszel

The system Quadlet runs the official
[`henrygd/beszel-agent`](https://www.beszel.dev/guide/agent-installation) image
with host networking, as recommended for host network statistics. Its tag and
multi-architecture digest are pinned in
[`beszel-agent.container`](system_files/usr/share/containers/systemd/beszel-agent.container)
and updated by Renovate. Data persists at `/var/lib/beszel-agent`.

The unit has `ConditionPathExists=/etc/beszel-agent.env`; an unconfigured host
boots normally and does not enter a restart loop. Create the file with exactly
these per-host values from the Beszel Hub:

```dotenv
KEY="ssh-ed25519 AAAA..."
TOKEN="..."
HUB_URL="https://beszel.example.com"
```

`KEY`, `TOKEN`, and `HUB_URL` are the current required agent variables. The
image supplies `LISTEN=45876` and `DATA_DIR=/var/lib/beszel-agent`. If the Hub
only uses the outbound WebSocket connection, add `DISABLE_SSH=true` to avoid an
incoming SSH listener. Install the file as `root:root` mode `0600`, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl start beszel-agent.service
sudo systemctl status beszel-agent.service
```

uCore's rootful Podman socket is present at `/run/podman/podman.sock`; the
Quadlet activates it and mounts it at `/var/run/docker.sock`, where Beszel's
Docker-compatible monitor expects it. Podman's API is Docker-compatible, but
socket access is effectively root-equivalent even with a read-only bind mount.
The Quadlet follows Podman's required SELinux handling for socket access. Use a
filtering socket proxy in Ansible if that risk is unacceptable.

Podman automatic container updates are intentionally not enabled. A digest pin
cannot float, and the controlled update path is Renovate PR → native CI → signed
braunicore OS update. This also avoids an agent changing independently of the
host image.

## Fish users

The image guarantees `/usr/bin/fish` but does not create users or edit a
machine's passwd database. A current Fedora CoreOS Butane snippet is:

```yaml
variant: fcos
version: 1.7.0
passwd:
  users:
    - name: example
      shell: /usr/bin/fish
```

For an existing host, verify the binary before changing the account:

```yaml
- name: Check that Fish is in the deployed image
  ansible.builtin.stat:
    path: /usr/bin/fish
  register: fish_binary

- name: Use Fish as the login shell
  ansible.builtin.user:
    name: "{{ fleet_user }}"
    shell: /usr/bin/fish
  when: fish_binary.stat.exists and fish_binary.stat.executable
```

## Build and test locally

Podman and `just` follow the upstream template workflow:

```bash
just build braunicore dev
sudo just ostree-rechunk braunicore dev
sudo podman run --rm --entrypoint /bin/bash braunicore:dev -lc \
  'bootc container lint && test -x /usr/bin/fish && rpm -q fish tmux tailscale podman moby-engine'
```

Docker BuildKit can perform a quick non-rechunked development build:

```bash
docker build --pull -f Containerfile -t braunicore:dev .
docker run --rm --entrypoint /bin/bash braunicore:dev -lc \
  'bootc container lint && test -x /usr/bin/fish'
```

CI additionally runs the Podman system generator and `systemd-analyze verify`
against the generated Beszel service.

## Signing and recovery

Every architecture manifest and multi-architecture index is signed with the
dedicated public key in [`cosign.pub`](cosign.pub). Its SHA-256 is:

```text
873b12b4337d06414daeeab6032b088ee7769280fbd641f2c966647b9797c7da
```

The encrypted private key is supplied to Actions as `SIGNING_SECRET`; its
separate passphrase is `SIGNING_PASSWORD`. Neither belongs in Git, Ignition,
Ansible inventory, logs, or the image. Keep an offline encrypted recovery copy
of `cosign.key` and store its passphrase separately (for example, an encrypted
removable backup in a safe plus a password-manager record). Test recovery by
signing a disposable registry image, and record key rotation as a reviewed
policy transition. Losing both GitHub secrets and the recovery copy requires a
fleet trust-policy migration.

Cosign 3 is instructed to emit the legacy attachment format currently consumed
by the containers/image `sigstoreSigned` policy used by bootc/rpm-ostree. The
build merges only the exact `ghcr.io/herobrauni/braunicore` scope into uCore's
existing `/etc/containers/policy.json` and preserves all upstream scopes.

## Install, switch, update, and roll back

See [`docs/switching.md`](docs/switching.md) for exact preflight, initial trust
bootstrap, `bootc switch --enforce-container-sigpolicy`, verification, reboot,
post-boot, automatic-update, and rollback commands. Do not run the switch fleet
wide; validate one disposable VPS and retain console access first.

The installation architecture remains the official Fedora CoreOS metal raw
image → Ignition → OCI transition. No per-release braunicore disk image is
built. [`docs/reinstall.md`](docs/reinstall.md) records the already-available
opt-in `--ucore-image` setting in the local `herobrauni/reinstall` fork.

## Image, Ignition, and Ansible boundaries

- Image: identical fleet-wide RPMs, immutable vendor Quadlets, public trust
  roots, and secret-free defaults.
- Ignition: first-boot users, SSH keys, storage/networking, hostname, and the
  initial FCOS-to-braunicore transition.
- Ansible: Beszel environment files, Tailscale enrollment, account changes,
  firewalls, host-specific mounts, and other per-host agents.

Tailscale activation/authentication stays in Ansible. PatchMon and similar
agents remain future Ansible provisioning until they have a clean, secret-free,
bootc-compatible vendor unit.

## Failed Renovate updates

Open the dependency PR's `Build and publish` checks and identify whether amd64
or arm64 failed. Reproduce with `just build`, inspect the `dnf5`, bootc lint, or
Quadlet error, and leave the PR unmerged until both native jobs pass. Closing a
bad PR leaves `stable` untouched; Renovate will propose a later update. Never
resolve a failure by removing the digest pin or signature checks.

See [`MAINTENANCE.md`](MAINTENANCE.md) for the short maintenance policy.
