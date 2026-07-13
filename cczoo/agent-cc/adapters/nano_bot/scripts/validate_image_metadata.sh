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

# Validates the image identity selected before deployment against the image
# identity reported by Kubernetes after the guest-pull workload starts.
set -euo pipefail

CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"
CONTAINER_NAME="${CONTAINER_NAME:-asterinas-coco-tdx}"
POD_NAME="${POD_NAME:-nano-bot-kata-qemu-tdx-linux}"
IMAGE_REFERENCE="${IMAGE_REFERENCE:-${NANO_BOT_IMAGE:-}}"
IMAGE_INSPECT_REFERENCE="${IMAGE_INSPECT_REFERENCE:-}"
EXPECTED_MANIFEST_DIGEST="${EXPECTED_MANIFEST_DIGEST:-}"
COSIGN_PUBLIC_KEY="${COSIGN_PUBLIC_KEY:-${IMAGE_METADATA_COSIGN_KEY:-}}"
SIGNED_IMAGES_ENABLED="${SIGNED_IMAGES_ENABLED:-0}"
SIGNED_IMAGES_KBS_URL="${SIGNED_IMAGES_KBS_URL:-}"
SIGNED_IMAGES_POLICY="${SIGNED_IMAGES_POLICY:-}"
REPORT_FILE="${REPORT_FILE:-/tmp/${POD_NAME}.image-metadata.json}"

stamp() { date +"%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(stamp)] $*"; }
err() { echo "[$(stamp)] ERROR: $*" >&2; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || { err "Required command not found: $1"; exit 1; }; }

need_cmd "$CONTAINER_ENGINE"
need_cmd jq
need_cmd skopeo

[[ -n "$IMAGE_REFERENCE" ]] || { err "IMAGE_REFERENCE or NANO_BOT_IMAGE is required."; exit 1; }
[[ -n "$IMAGE_INSPECT_REFERENCE" ]] || {
  err "IMAGE_INSPECT_REFERENCE is required, for example 127.0.0.1:5000/library/nano_bot:2.0."
  exit 1
}

if [[ "$SIGNED_IMAGES_ENABLED" == "1" ]]; then
  need_cmd cosign
  [[ -n "$COSIGN_PUBLIC_KEY" ]] || { err "IMAGE_METADATA_COSIGN_KEY is required when signed images are enabled."; exit 1; }
  [[ -f "$COSIGN_PUBLIC_KEY" ]] || { err "Cosign public key not found: $COSIGN_PUBLIC_KEY"; exit 1; }
  [[ -n "$SIGNED_IMAGES_KBS_URL" && -n "$SIGNED_IMAGES_POLICY" ]] || {
    err "SIGNED_IMAGES_KBS_URL and SIGNED_IMAGES_POLICY are required when signed images are enabled."
    exit 1
  }
fi

skopeo_args=()
if [[ "$IMAGE_INSPECT_REFERENCE" == *"127.0.0.1:"* || "$IMAGE_INSPECT_REFERENCE" == *"localhost:"* ]]; then
  skopeo_args+=(--tls-verify=false)
fi

metadata="$(skopeo inspect "${skopeo_args[@]}" "docker://${IMAGE_INSPECT_REFERENCE}")"
manifest_digest="$(jq -er '.Digest' <<<"$metadata")"
layer_digests="$(jq -c '.Layers // []' <<<"$metadata")"
raw_metadata="$(skopeo inspect --raw "${skopeo_args[@]}" "docker://${IMAGE_INSPECT_REFERENCE}")"
config_digest="$(jq -er '.config.digest // empty' <<<"$raw_metadata")"
[[ -n "$config_digest" ]] || { err "Image manifest has no config digest."; exit 1; }

if [[ -n "$EXPECTED_MANIFEST_DIGEST" && "$manifest_digest" != "$EXPECTED_MANIFEST_DIGEST" ]]; then
  err "Manifest digest mismatch before deployment: expected $EXPECTED_MANIFEST_DIGEST, got $manifest_digest."
  exit 1
fi

if [[ "$SIGNED_IMAGES_ENABLED" == "1" ]]; then
  log "Verifying cosign signature for ${IMAGE_INSPECT_REFERENCE}@${manifest_digest}."
  cosign verify --insecure-ignore-tlog --allow-insecure-registry \
    --key "$COSIGN_PUBLIC_KEY" \
    "${IMAGE_INSPECT_REFERENCE}@${manifest_digest}" >/dev/null
fi

pod_json="$("$CONTAINER_ENGINE" exec "$CONTAINER_NAME" kubectl get pod "$POD_NAME" -o json)"
actual_image="$(jq -er '.spec.containers[0].image' <<<"$pod_json")"
actual_image_id="$(jq -er '.status.containerStatuses[0].imageID' <<<"$pod_json")"
actual_digest="$(sed -n 's/.*@\(sha256:[0-9a-fA-F]\{64\}\).*/\1/p' <<<"$actual_image_id")"
[[ -n "$actual_digest" ]] || { err "Pod imageID has no sha256 digest: $actual_image_id"; exit 1; }

if [[ "$actual_digest" != "$manifest_digest" ]]; then
  err "Pod image digest mismatch: expected $manifest_digest, got $actual_digest."
  exit 1
fi

if [[ "$actual_image" != "$IMAGE_REFERENCE" ]]; then
  err "Pod image reference mismatch: expected $IMAGE_REFERENCE, got $actual_image."
  exit 1
fi

annotation="$(jq -r '.metadata.annotations["io.katacontainers.config.hypervisor.kernel_params"] // ""' <<<"$pod_json")"
if [[ "$SIGNED_IMAGES_ENABLED" == "1" ]]; then
  for token in \
    "agent.aa_kbc_params=cc_kbc::${SIGNED_IMAGES_KBS_URL}" \
    "agent.image_policy_file=${SIGNED_IMAGES_POLICY}" \
    "agent.enable_signature_verification=true"; do
    if ! grep -Fq -- "$token" <<<"$annotation"; then
      err "Pod annotation is missing required signed-image token: $token"
      exit 1
    fi
  done
fi

jq -n \
  --arg image_reference "$IMAGE_REFERENCE" \
  --arg inspect_reference "$IMAGE_INSPECT_REFERENCE" \
  --arg manifest_digest "$manifest_digest" \
  --arg config_digest "$config_digest" \
  --arg actual_image "$actual_image" \
  --arg actual_image_id "$actual_image_id" \
  --arg actual_digest "$actual_digest" \
  --arg annotation "$annotation" \
  --argjson layer_digests "$layer_digests" \
  '{image_reference: $image_reference,
    inspect_reference: $inspect_reference,
    manifest_digest: $manifest_digest,
    config_digest: $config_digest,
    layer_digests: $layer_digests,
    pod_image: $actual_image,
    pod_image_id: $actual_image_id,
    pod_digest: $actual_digest,
    signed_image_annotation: $annotation,
    manifest_matches_pod: ($manifest_digest == $actual_digest)}' > "$REPORT_FILE"

log "Image metadata validation passed."
log "Manifest digest: $manifest_digest"
log "Pod imageID: $actual_image_id"
log "Report: $REPORT_FILE"
