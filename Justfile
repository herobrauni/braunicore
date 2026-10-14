set dotenv-filename := "image-template.env"
set dotenv-load := true

export image_name := env_var("IMAGE_NAME")
export repo_organization := env_var("REPO_ORGANIZATION")
export image_desc := env_var("IMAGE_DESC")
export default_tag := env_var("DEFAULT_TAG")

[private]
default:
    @just --list

check:
    just --unstable --fmt --check -f Justfile

# Native Podman build, following ublue-os/image-template conventions.
build target_image=image_name tag=default_tag:
    #!/usr/bin/env bash
    set -euo pipefail
    labels=(
      --label "org.opencontainers.image.description={{ image_desc }}"
      --label "org.opencontainers.image.source=https://github.com/{{ repo_organization }}/{{ image_name }}"
      --label "org.opencontainers.image.title={{ image_name }}"
      --label "org.opencontainers.image.vendor={{ repo_organization }}"
    )
    podman build --pull=newer "${labels[@]}" --tag "{{ target_image }}:{{ tag }}" --file Containerfile .

# The template's supported rpm-ostree rechunker minimizes bootc update deltas.
ostree-rechunk target_image=image_name tag=default_tag:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "${UID}" -ne 0 ]]; then
      echo "ostree-rechunk must run as root" >&2
      exit 1
    fi
    podman run --rm \
      --pull=never \
      --privileged \
      --volume /var/lib/containers:/var/lib/containers \
      --entrypoint /usr/bin/rpm-ostree \
      "localhost/{{ target_image }}:{{ tag }}" \
      compose build-chunked-oci \
      --max-layers 127 \
      --format-version=2 \
      --bootc \
      --from "localhost/{{ target_image }}:{{ tag }}" \
      --output "containers-storage:localhost/{{ target_image }}:{{ tag }}"

# Validate built image contract, packages, and services locally.
validate target_image=image_name tag=default_tag:
    #!/usr/bin/env bash
    set -euo pipefail
    podman run --rm --entrypoint /bin/bash "{{ target_image }}:{{ tag }}" -lc '
      set -euo pipefail
      bootc container lint
      for command in fish wget htop btop rg fd tree ncdu uv chezmoi incus; do
        command -v "${command}"
      done
      rpm -q fish wget2-wget htop btop ripgrep fd-find tree ncdu uv chezmoi \
        incus incus-agent \
        tmux tailscale podman moby-engine bootc rpm-ostree
      if rpm -q atuin; then
        echo "Atuin must not be installed as an RPM" >&2
        exit 1
      fi
    '
