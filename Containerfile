# Keep build inputs out of the final image layers.
FROM scratch AS ctx
COPY build_files /
COPY system_files /system_files

# Renovate updates the stable tag's digest after pull-request CI passes.
FROM ghcr.io/ublue-os/ucore-minimal:stable@sha256:0dc91f56e10f4841cdb7d4f2561fc209cb89ecf1c00d3ab0f91f22f864de0d85

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache/libdnf5 \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh

RUN ["bootc", "container", "lint"]
