# Opt-in reinstall target

The local fork at `/home/brauni/Repos/reinstall` was inspected on branch
`feature/coreos-ucore`. It already implements the desired architecture:

```text
official signed Fedora CoreOS metal raw image
  -> Ignition
  -> first unverified OCI rebase
  -> second containers/image-policy-verified OCI rebase
```

It also already exposes `--ucore-image`; therefore the smallest safe change is
no code change and no changed default. Opt in per installation:

```bash
sudo bash /tmp/reinstall.sh ucore-minimal \
  --stream stable \
  --ucore-image ghcr.io/herobrauni/braunicore:stable \
  --ignition-file /path/to/host.ign \
  --target-disk /dev/vda
```

The existing `ucore-minimal` default remains
`ghcr.io/ublue-os/ucore-minimal:stable`. During the opt-in two-stage transition,
the first braunicore deployment installs its public key and exact policy scope;
the second deployment selects the same reference using
`ostree-image-signed:docker://...`. New OS releases then arrive through the OCI
tag rather than maintained custom raw disks.

Do not change the fork's default until the public image and signature have been
validated on a disposable VPS. A future convenience alias named `braunicore`
could simply set the same `ucore_image` variable, but it is not necessary and
would add another code path to test.
