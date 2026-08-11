set dotenv-filename := "image-template.env"
set dotenv-load

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
