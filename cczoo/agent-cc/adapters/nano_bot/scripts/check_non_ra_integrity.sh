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

# Reports integrity capabilities that can be enabled without Remote
# Attestation. This script deliberately does not claim measured-rootfs or
# dm-verity support when the guest lacks the required implementation.
set -euo pipefail

CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"
CONTAINER_NAME="${CONTAINER_NAME:-asterinas-coco-official}"
POD_NAME="${POD_NAME:-nano-bot-kata-qemu-tdx-linux}"
REPORT_FILE="${REPORT_FILE:-/tmp/${POD_NAME}.non-ra-integrity.json}"

stamp() { date +"%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(stamp)] $*"; }
err() { echo "[$(stamp)] ERROR: $*" >&2; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || { err "Required command not found: $1"; exit 1; }; }

need_cmd "$CONTAINER_ENGINE"
need_cmd jq

container_exec() {
  "$CONTAINER_ENGINE" exec "$CONTAINER_NAME" bash -lc "$*"
}

[[ -n "$CONTAINER_NAME" ]] || { err "CONTAINER_NAME is required."; exit 1; }
"$CONTAINER_ENGINE" ps --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME" || {
  err "Container is not running: $CONTAINER_NAME"
  exit 1
}

nydus_running=false
if container_exec "pgrep -af 'containerd-nydus-grpc' >/dev/null"; then
  nydus_running=true
fi

nydus_config=false
if container_exec "test -s /etc/nydus/config-proxy.toml && grep -q 'fs_driver = \"proxy\"' /etc/nydus/config-proxy.toml"; then
  nydus_config=true
fi

guest_pull=false
if container_exec "test -s /opt/coco/config/configuration-qemu-tdx-linux.toml"; then
  guest_pull=true
fi

pod_running=false
if container_exec "kubectl get pod '$POD_NAME' -o jsonpath='{.status.phase}' 2>/dev/null | grep -qx Running"; then
  pod_running=true
fi

confidential_emptydir=false
pod_json="$(container_exec "kubectl get pod '$POD_NAME' -o json 2>/dev/null" || true)"
if [[ -n "$pod_json" ]] && jq -e '
  any(.spec.volumes[]?; .name == "confidential-workdir" and
    (.emptyDir? != null) and ((.emptyDir.medium // "") == "")) and
  all(.spec.containers[]?.volumeMounts[]?;
    (.name != "confidential-workdir") or
    (.mountPath == "/tmp" or .mountPath == "/var/tmp" or
     .mountPath == "/root/.config" or .mountPath == "/root/.local"))
' >/dev/null 2>&1 <<<"$pod_json"; then
  confidential_emptydir=true
fi

kernel_config=""
if container_exec "zcat /proc/config.gz 2>/dev/null | grep -E 'CONFIG_DM_VERITY|CONFIG_BLK_DEV_DM'" >/tmp/non-ra-kernel-config.$$ 2>/dev/null; then
  kernel_config="$(tr '\n' ';' < /tmp/non-ra-kernel-config.$$)"
else
  kernel_config="unavailable"
fi
rm -f /tmp/non-ra-kernel-config.$$

dm_verity_kernel=false
if [[ "$kernel_config" == *"CONFIG_DM_VERITY=y"* || "$kernel_config" == *"CONFIG_DM_VERITY=m"* ]]; then
  dm_verity_kernel=true
fi

dm_tools=false
if container_exec "command -v dmsetup >/dev/null 2>&1 && command -v veritysetup >/dev/null 2>&1"; then
  dm_tools=true
fi

if [[ "$nydus_running" == true && "$nydus_config" == true && "$guest_pull" == true && "$pod_running" == true ]]; then
  nydus_status=ready
else
  nydus_status=not_ready
fi

if [[ "$dm_verity_kernel" == true && "$dm_tools" == true ]]; then
  dm_verity_status=prerequisites_present
else
  dm_verity_status=not_available
fi

jq -n \
  --arg container "$CONTAINER_NAME" \
  --arg pod "$POD_NAME" \
  --arg kernel_config "$kernel_config" \
  --arg nydus_status "$nydus_status" \
  --arg dm_verity_status "$dm_verity_status" \
  --argjson confidential_emptydir "$confidential_emptydir" \
  --argjson nydus_running "$nydus_running" \
  --argjson nydus_config "$nydus_config" \
  --argjson guest_pull "$guest_pull" \
  --argjson pod_running "$pod_running" \
  --argjson dm_verity_kernel "$dm_verity_kernel" \
  --argjson dm_tools "$dm_tools" \
  '{container: $container,
    pod: $pod,
    remote_attestation_required: false,
    confidential_emptydir: {
      configured: $confidential_emptydir,
      volume: "confidential-workdir",
      medium: "block-backed emptyDir (LUKS2 under confidential runtime)"
    },
    nydus_guest_pull: {
      status: $nydus_status,
      snapshotter_running: $nydus_running,
      proxy_config_present: $nydus_config,
      guest_pull_path_detected: $guest_pull,
      workload_running: $pod_running
    },
    dm_verity: {
      status: $dm_verity_status,
      kernel_config: $kernel_config,
      kernel_support: $dm_verity_kernel,
      guest_tools_present: $dm_tools
    },
    measured_rootfs: {
      status: "deferred_until_remote_attestation",
      remote_attestation_required: true
    }}' > "$REPORT_FILE"

log "Non-RA integrity capability report: $REPORT_FILE"
log "Nydus/guest-pull status: $nydus_status"
log "dm-verity status: $dm_verity_status"
log "Measured RootFS: deferred until Remote Attestation is available"

[[ "$nydus_status" == ready ]]
