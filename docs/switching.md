# Switching a test VPS to braunicore

Do this on one disposable/canary VPS with working provider-console access. The
commands below are documentation only; this repository does not execute them.

## 1. Preflight

Confirm the machine is already booted through bootc/rpm-ostree, has enough free
space, has no pending deployment, uses a supported architecture, and can reach
GHCR:

```bash
uname -m
sudo bootc status --format yaml
rpm-ostree status
df -h / /boot /var
systemctl is-enabled rpm-ostreed-automatic.timer
sudo skopeo inspect docker://ghcr.io/herobrauni/braunicore:stable | \
  jq '{Name, Digest, Architecture, Os}'
```

Supported values are `x86_64` (mandatory) and `aarch64` (built on GitHub's
native arm64 runner). Resolve any failed deployment and take a provider snapshot
if that is part of the VPS recovery plan.

## 2. Bootstrap trust for the first switch

The currently booted ublue-os image trusts `ghcr.io/ublue-os`, not this new
repository. Install the braunicore public key and Sigstore attachment mapping,
then merge one exact policy scope. This is the only trust transition; the
braunicore image carries the same key and scope for subsequent updates.

Download `cosign.pub` from a reviewed commit and verify its fingerprint before
installing it:

```bash
echo '873b12b4337d06414daeeab6032b088ee7769280fbd641f2c966647b9797c7da  cosign.pub' | sha256sum -c -
sudo install -D -o root -g root -m 0644 cosign.pub /etc/pki/containers/braunicore.pub

sudo install -d -o root -g root -m 0755 /etc/containers/registries.d
printf '%s\n' \
  'docker:' \
  '  ghcr.io/herobrauni/braunicore:' \
  '    use-sigstore-attachments: true' | \
  sudo tee /etc/containers/registries.d/braunicore.yaml >/dev/null
sudo chmod 0644 /etc/containers/registries.d/braunicore.yaml

policy_tmp=$(mktemp)
sudo jq '.transports.docker["ghcr.io/herobrauni/braunicore"] = [{
  "type":"sigstoreSigned",
  "keyPath":"/etc/pki/containers/braunicore.pub",
  "signedIdentity":{"type":"matchRepository"}
}]' /etc/containers/policy.json > "${policy_tmp}"
sudo install -o root -g root -m 0644 "${policy_tmp}" /etc/containers/policy.json
rm -f "${policy_tmp}"

sudo jq -e '.transports.docker["ghcr.io/ublue-os"] and
  .transports.docker["ghcr.io/herobrauni/braunicore"][0].type == "sigstoreSigned"' \
  /etc/containers/policy.json
```

The final `jq` assertion proves the uBlue scope was preserved.

## 3. Select the signed image

Use bootc's current switch command and explicitly enforce containers/image
policy. Do not add `--apply`; inspect the staged deployment before rebooting.

```bash
sudo bootc switch --enforce-container-sigpolicy \
  ghcr.io/herobrauni/braunicore:stable
sudo bootc status --format yaml
rpm-ostree status
```

A signature-policy error must stop here. Do not bypass it. For an independent
full pull through the same policy (which consumes disk and bandwidth), use:

```bash
verify_dir=$(mktemp -d)
sudo skopeo --policy /etc/containers/policy.json copy \
  docker://ghcr.io/herobrauni/braunicore:stable \
  "dir:${verify_dir}"
sudo rm -rf "${verify_dir}"
```

Reboot only after the staged image reference and digest are correct:

```bash
sudo systemctl reboot
```

## 4. Post-boot validation

```bash
sudo bootc status --booted --format yaml
rpm-ostree status
test -x /usr/bin/fish
rpm -q fish tmux tailscale podman moby-engine bootc rpm-ostree
sudo bootc container lint
systemctl status rpm-ostreed-automatic.timer
systemctl status beszel-agent.service  # "skipped" is expected until configured
```

`bootc status` must show the booted image reference as
`ghcr.io/herobrauni/braunicore:stable`, not the ublue-os base. Once
`/etc/beszel-agent.env` exists, validate `systemctl status beszel-agent` and
`sudo podman ps --filter name=beszel-agent`.

## 5. Automatic updates

uCore minimal already enables `rpm-ostreed-automatic.timer`; braunicore does not
replace its policy or schedule. The local reinstall fork can set it to apply at
04:00 Europe/Berlin. Confirm both the tracked origin and timer:

```bash
sudo bootc status --booted --format yaml
systemctl is-enabled rpm-ostreed-automatic.timer
systemctl list-timers rpm-ostreed-automatic.timer
grep '^AutomaticUpdatePolicy=' /etc/rpm-ostreed.conf
journalctl -u rpm-ostreed-automatic.service --since yesterday
```

Because the tracked reference is now the braunicore `stable` tag, daily/nightly
checks follow braunicore; Renovate and CI decide when that tag advances.

## 6. Rollback

If the new deployment boots but is unhealthy, stop the automatic updater while
investigating, queue the rollback deployment, inspect it, and reboot:

```bash
sudo systemctl stop rpm-ostreed-automatic.timer
sudo bootc rollback
sudo bootc status --format yaml
sudo systemctl reboot
```

If it does not boot, select the previous deployment in the provider console or
bootloader menu. After recovery, run `bootc status` and keep the timer stopped
until the bad release is understood. Re-enable it only after the tracked image
reference is deliberately set to a working tag:

```bash
sudo systemctl enable --now rpm-ostreed-automatic.timer
```

Rollback reorders OS deployments; `/var` data remains. Machine-local `/etc`
state follows bootc's deployment merge semantics, so retain backups of critical
host configuration.
