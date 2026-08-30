#!/bin/bash

set -ouex pipefail

cp -avf /ctx/system_files/. /

# One package per line. Blank lines and comments are ignored.
mapfile -t packages < <(sed -e 's/[[:space:]]*#.*$//' -e '/^[[:space:]]*$/d' /ctx/packages.txt)
if (( ${#packages[@]} > 0 )); then
    dnf5 install -y "${packages[@]}"
fi

# Add only our exact repository scope to uCore's policy. Preserve every
# upstream transport and trust scope verbatim.
# The signing RPM stages the hardened policy; /usr/etc is the documented
# location (ucore#430: recent builds leave a corrupted insecure default at
# /etc and no longer ship /usr/etc, so fall back to the staged copy).
policy_src="/usr/etc/containers/policy.json"
if [[ ! -f "${policy_src}" ]]; then
    policy_src="/usr/share/ublue-os/signing/usr/etc/containers/policy.json"
fi
jq -e '.default[0].type == "reject" and .transports.docker["ghcr.io/ublue-os"]' \
    "${policy_src}" >/dev/null
policy_tmp="$(mktemp)"
jq '.transports.docker["ghcr.io/herobrauni/braunicore"] = [{
        "type": "sigstoreSigned",
        "keyPath": "/etc/pki/containers/braunicore.pub",
        "signedIdentity": {"type": "matchRepository"}
    }]' "${policy_src}" > "${policy_tmp}"
install -m 0644 "${policy_tmp}" /etc/containers/policy.json

# Fail the build immediately if our intentionally small contract is broken.
for command in fish wget htop btop rg fd tree ncdu uv chezmoi incus; do
    command -v "${command}"
done
rpm -q "${packages[@]}" incus incus-agent tmux tailscale podman moby-engine bootc rpm-ostree
# Atuin is owned by the Braunsible pinned release role and must not be layered.
if rpm -q atuin; then
    echo "Atuin must not be installed as an RPM" >&2
    exit 1
fi
# Incus runs under enforcing SELinux via container-selinux contexts; there is
# no dedicated policy since 6.23. Fail early if a base change drops them.
test "$(matchpathcon -n /usr/libexec/incus/incusd)" = \
    "system_u:object_r:container_runtime_exec_t:s0"
test -S /run/podman/podman.sock || systemctl cat podman.socket >/dev/null
QUADLET_UNIT_DIRS=/usr/share/containers/systemd \
    /usr/lib/systemd/system-generators/podman-system-generator --dryrun >/dev/null

# Package-manager state is build-time data, not host state. RPM scriptlets and
# dnf5's global systemd-tmpfiles pass materialize runtime directories in /var
# during the build; the booted host recreates them via tmpfiles on first boot.
# Restore uCore's pristine skeleton so bootc lint remains warning-free.
dnf5 clean all
rm -rf /run/dnf /var/lib/dnf /var/cache/ldconfig
find /var -mindepth 1 -maxdepth 1 \
    ! -name cache ! -name log ! -name run ! -name tmp -exec rm -rf {} +
ostree container commit
