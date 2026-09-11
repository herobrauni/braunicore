# Keep build inputs out of the final image layers.
FROM scratch AS ctx
COPY build_files /
COPY system_files /system_files

# Renovate updates the stable tag's digest after pull-request CI passes.
FROM ghcr.io/ublue-os/ucore-minimal:stable@sha256:1185e32d4d2940417d2d926a189a9e19793137c05e786e81b56de914250b122d

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache/libdnf5 \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh

RUN ["bootc", "container", "lint"]
