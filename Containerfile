# Keep build inputs out of the final image layers.
FROM scratch AS ctx
COPY build_files /
COPY system_files /system_files

# Renovate updates the stable tag's digest after pull-request CI passes.
FROM ghcr.io/ublue-os/ucore-minimal:stable@sha256:2c76b8a7f29e16bc68dddd7b883d63916bb5c0519bce305210dc653ecd88b966

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache/libdnf5 \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh

RUN ["bootc", "container", "lint"]
