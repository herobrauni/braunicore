# Keep build inputs out of the final image layers.
FROM scratch AS ctx
COPY build_files /
COPY system_files /system_files

# Build the small Nix file-context module outside the final image so policy
# development tools do not become host packages.
FROM ghcr.io/ublue-os/ucore-minimal:stable@sha256:db3dec6aa99ec75f25c8a916807d23d3927fd2b72a7dfefd8eddf08b2d029d71 AS policy-builder
RUN dnf install -y selinux-policy-devel && dnf clean all
COPY build_files/selinux /src
RUN make -f /usr/share/selinux/devel/Makefile -C /src braunicore_nix.pp

# Renovate updates the stable tag's digest after pull-request CI passes.
FROM ghcr.io/ublue-os/ucore-minimal:stable@sha256:db3dec6aa99ec75f25c8a916807d23d3927fd2b72a7dfefd8eddf08b2d029d71

COPY --from=policy-builder /src/braunicore_nix.pp /usr/share/selinux/packages/braunicore_nix.pp

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache/libdnf5 \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh

RUN ["bootc", "container", "lint"]
