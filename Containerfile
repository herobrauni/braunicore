# Keep build inputs out of the final image layers.
FROM scratch AS ctx
COPY build_files /
COPY system_files /system_files

# Renovate updates the stable tag's digest after pull-request CI passes.
FROM ghcr.io/ublue-os/ucore-minimal:stable@sha256:7bbf025e14752c5e29008ed5aa9b36d407ae1523b53a11937000ce1f9b330b50

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache/libdnf5 \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh

RUN ["bootc", "container", "lint"]
