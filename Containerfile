# Keep build inputs out of the final image layers.
FROM scratch AS ctx
COPY build_files /
COPY system_files /system_files

# Renovate updates the stable tag's digest after pull-request CI passes.
FROM ghcr.io/ublue-os/ucore-minimal:stable@sha256:280c058bb3910e2983eed2b48866e79e6f0f8872c984eda97d99d7e671dab45f

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache/libdnf5 \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh

RUN ["bootc", "container", "lint"]
