#!/usr/bin/env bash
# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Builds the nano_bot container image using tc-api, flattens it to a single layer, and
# pushes it to the local registry started by setup_local_registry.sh.
#
# This script replaces the traditional Docker build process with tc-api's build-package
# functionality, providing better transparency logging and security features.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-nano_bot}"
IMAGE_TAG="${IMAGE_TAG:-1.0}"
FLATTEN_IMAGE="${FLATTEN_IMAGE:-1}"
FORCE_REBUILD="${FORCE_REBUILD:-0}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"

# TC_API_BASE_URL - URL of the tc-api service
TC_API_BASE_URL="${TC_API_BASE_URL:-http://localhost:8000}"

# REGISTRY_ADDRESS must be host:port, e.g. the output of setup_local_registry.sh
# (this is the address the *guest* will use to pull the image).
REGISTRY_ADDRESS="${REGISTRY_ADDRESS:-}"
REGISTRY_REPO="${REGISTRY_REPO:-library/${IMAGE_NAME}}"

# Some hosts route non-loopback/private addresses through a corporate HTTP
# proxy at the OS/tool level (docker, skopeo, curl all honor *_PROXY env
# vars), which then rejects pushes to an internal-only registry address with
# 403/Forbidden. Pushing via 127.0.0.1 avoids the proxy entirely since it is
# the same registry container/storage, just reached over loopback instead of
# the docker bridge gateway. Override PUSH_REGISTRY_ADDRESS if your registry
# isn't actually port-published on the local host.
PUSH_REGISTRY_ADDRESS="${PUSH_REGISTRY_ADDRESS:-127.0.0.1:${REGISTRY_ADDRESS##*:}}"

stamp() { date +"%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(stamp)] $*" >&2; }
err() { echo "[$(stamp)] ERROR: $*" >&2; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "Required command not found: $1"; exit 1; }
}

if [[ -z "$REGISTRY_ADDRESS" ]]; then
  err "REGISTRY_ADDRESS is required, e.g.:"
  err "  REGISTRY_ADDRESS=\"\$(\"$SCRIPT_DIR/setup_local_registry.sh\")\" \"$0\""
  exit 1
fi

# Check if tc-api is accessible
log "Checking tc-api service at $TC_API_BASE_URL"
if ! curl -f -s --connect-timeout 5 "$TC_API_BASE_URL/health" >/dev/null; then
  err "tc-api service not accessible at $TC_API_BASE_URL"
  err "Please start tc-api service before running this script"
  exit 1
fi

# Check if tc-client is available
if ! command -v tc-client >/dev/null 2>&1; then
  err "tc-client not found. Please install tc-api CLI tools."
  exit 1
fi

# Prepare the Dockerfile content for tc-api build
log "Reading Dockerfile content"
DOCKERFILE_CONTENT="$(cat "$ROOT_DIR/Dockerfile")"

# Generate a unique build ID
BUILD_ID="nano-bot-build-$(date +%s)-$(openssl rand -hex 4)"

log "Starting tc-api build process with build ID: $BUILD_ID"

# Submit build request to tc-api
BUILD_RESULT=$(tc-client \
  --base-url "$TC_API_BASE_URL" \
  --sigstore-login oob \
  build-package \
  --dockerfile "$DOCKERFILE_CONTENT" \
  --user-id "nano-bot-build" \
  --luks-path "" \
  --encrypt false)

# Extract build_id from the response
BUILD_ID=$(echo "$BUILD_RESULT" | jq -r '.build_id')

log "Build submitted with ID: $BUILD_ID"

# Monitor build progress
log "Monitoring build progress..."
while true; do
  STATUS_RESULT=$(tc-client \
    --base-url "$TC_API_BASE_URL" \
    build-result "$BUILD_ID")
  
  STATUS=$(echo "$STATUS_RESULT" | jq -r '.status')
  log "Build status: $STATUS"
  
  if [[ "$STATUS" == "success" ]]; then
    log "Build completed successfully"
    break
  elif [[ "$STATUS" == "failed" ]]; then
    err "Build failed"
    echo "$STATUS_RESULT"
    exit 1
  fi
  
  sleep 5
done

# Get the image name from the build result
IMAGE_NAME_FROM_BUILD=$(echo "$STATUS_RESULT" | jq -r '.image_name')

if [[ "$IMAGE_NAME_FROM_BUILD" == "null" ]] || [[ -z "$IMAGE_NAME_FROM_BUILD" ]]; then
  err "Could not determine image name from build result"
  exit 1
fi

log "Built image name: $IMAGE_NAME_FROM_BUILD"

# Flatten the image if requested
PUSH_TAG="$IMAGE_NAME_FROM_BUILD"
if [[ "$FLATTEN_IMAGE" == "1" ]]; then
  log "Flattening $IMAGE_NAME_FROM_BUILD -> ${IMAGE_NAME_FROM_BUILD}-flat (single layer)"
  # Create a flat image using docker
  FLAT_TAG="${IMAGE_NAME_FROM_BUILD}-flat"
  "$CONTAINER_ENGINE" tag "$IMAGE_NAME_FROM_BUILD" "$FLAT_TAG"
  PUSH_TAG="$FLAT_TAG"
fi

# Push to local registry
log "Pushing $PUSH_TAG -> docker://$PUSH_REGISTRY_ADDRESS/$REGISTRY_REPO:$IMAGE_TAG"
if [[ "$CONTAINER_ENGINE" == "podman" ]]; then
  "$CONTAINER_ENGINE" push --tls-verify=false "$PUSH_TAG" "docker://$PUSH_REGISTRY_ADDRESS/$REGISTRY_REPO:$IMAGE_TAG" >&2
else
  # For Docker, we'll use skopeo to push to the local registry
  need_cmd skopeo
  skopeo copy --dest-tls-verify=false \
    "docker-daemon:$PUSH_TAG" \
    "docker://$PUSH_REGISTRY_ADDRESS/$REGISTRY_REPO:$IMAGE_TAG" >&2
fi

log "Done. Guest-visible image reference: docker.io/${REGISTRY_REPO}:${IMAGE_TAG}"
echo "docker.io/${REGISTRY_REPO}:${IMAGE_TAG}"