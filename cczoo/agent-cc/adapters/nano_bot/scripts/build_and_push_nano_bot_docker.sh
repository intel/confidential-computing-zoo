#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"
IMAGE_NAME="${IMAGE_NAME:-nano_bot}"
IMAGE_TAG="${IMAGE_TAG:-2.0}"
REGISTRY_ADDRESS="${REGISTRY_ADDRESS:?Set REGISTRY_ADDRESS to the guest-reachable host:port}"
REGISTRY_REPO="${REGISTRY_REPO:-library/${IMAGE_NAME}}"
PUSH_REGISTRY_ADDRESS="${PUSH_REGISTRY_ADDRESS:-127.0.0.1:${REGISTRY_ADDRESS##*:}}"
IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"
ARCHIVE="${TMPDIR:-/tmp}/${IMAGE_NAME}-${IMAGE_TAG}.tar"

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || { echo "ERROR: required command not found: $1" >&2; exit 1; }
}

need_cmd "$CONTAINER_ENGINE"
need_cmd skopeo
need_cmd curl

echo "Building $IMAGE_REF with Docker"
"$CONTAINER_ENGINE" build \
    --build-arg http_proxy="${http_proxy:-}" \
    --build-arg https_proxy="${https_proxy:-}" \
    --build-arg HTTP_PROXY="${HTTP_PROXY:-}" \
    --build-arg HTTPS_PROXY="${HTTPS_PROXY:-}" \
    -t "$IMAGE_REF" "$ROOT_DIR"

echo "Checking registry at http://$PUSH_REGISTRY_ADDRESS"
NO_PROXY="$PUSH_REGISTRY_ADDRESS,127.0.0.1,localhost" \
no_proxy="$PUSH_REGISTRY_ADDRESS,127.0.0.1,localhost" \
curl -fsS --max-time 10 "http://$PUSH_REGISTRY_ADDRESS/v2/" >/dev/null

"$CONTAINER_ENGINE" save "$IMAGE_REF" -o "$ARCHIVE"
NO_PROXY="$PUSH_REGISTRY_ADDRESS,127.0.0.1,localhost" \
no_proxy="$PUSH_REGISTRY_ADDRESS,127.0.0.1,localhost" \
skopeo copy --retry-times 3 --format v2s2 \
    --dest-tls-verify=false \
    "docker-archive:$ARCHIVE" \
    "docker://$PUSH_REGISTRY_ADDRESS/$REGISTRY_REPO:$IMAGE_TAG"

echo "Guest image reference: docker.io/$REGISTRY_REPO:$IMAGE_TAG"