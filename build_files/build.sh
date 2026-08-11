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
policy_tmp="$(mktemp)"
jq '.transports.docker["ghcr.io/herobrauni/braunicore"] = [{
        "type": "sigstoreSigned",
        "keyPath": "/etc/pki/containers/braunicore.pub",
        "signedIdentity": {"type": "matchRepository"}
    }]' /etc/containers/policy.json > "${policy_tmp}"
install -m 0644 "${policy_tmp}" /etc/containers/policy.json

# Fail the build immediately if our intentionally small contract is broken.
test -x /usr/bin/fish
rpm -q fish tmux tailscale podman moby-engine bootc rpm-ostree
test -S /run/podman/podman.sock || systemctl cat podman.socket >/dev/null
QUADLET_UNIT_DIRS=/usr/share/containers/systemd \
    /usr/lib/systemd/system-generators/podman-system-generator --dryrun >/dev/null

# Package-manager state is build-time data, not host state. Keep /var and /run
# clean so bootc lint remains warning-free.
dnf5 clean all
rm -rf /run/dnf /var/lib/dnf /var/cache/ldconfig
ostree container commit
