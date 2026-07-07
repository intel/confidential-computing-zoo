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

# Configures both the host CoCo container and the guest (TDX VM) initrd to
# use the local plain-HTTP registry as a mirror for docker.io. This is what
# lets a locally-built, unpublished image (like nano_bot) be pulled by:
#   1. the host containerd (used for CRI bookkeeping), and
#   2. the guest's Confidential Data Hub (which does the *real* image pull
#      from inside the TDX VM for CoCo guest-pull workloads).
#
# Idempotent: safe to run multiple times. The initrd is only re-packed if its
# current registry-configuration.toml doesn't already have the right mirror.
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-asterinas-coco-tdx}"
REGISTRY_ADDRESS="${REGISTRY_ADDRESS:-}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"

# Path to the CDH registry config as staged on the host container. This is
# also where the reference "confidential-data-hub-wrapper.sh"/proxy patches
# in this environment stage their inputs before baking them into the initrd.
CDH_REGISTRY_CONFIG="${CDH_REGISTRY_CONFIG:-/opt/coco/config/cdh/registry-configuration.toml}"

# initrd shared by all Kata/QEMU/TDX runtime classes in this environment.
LINUX_INITRD="${LINUX_INITRD:?LINUX_INITRD is required, e.g. /opt/coco/prebuilt/asterinas-coco/kata-containers-initrd.img}"

stamp() { date +"%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(stamp)] $*"; }
err() { echo "[$(stamp)] ERROR: $*" >&2; }

docker_exec() {
  "$CONTAINER_ENGINE" exec "$CONTAINER_NAME" bash -lc "$*"
}

if [[ -z "$REGISTRY_ADDRESS" ]]; then
  err "REGISTRY_ADDRESS is required, e.g.:"
  err "  REGISTRY_ADDRESS=\"\$(scripts/setup_local_registry.sh)\" \"$0\""
  exit 1
fi

configure_host_containerd_mirror() {
  log "Configuring host containerd docker.io mirror -> http://$REGISTRY_ADDRESS"
  docker_exec "mkdir -p /etc/containerd/certs.d/docker.io"
  "$CONTAINER_ENGINE" exec -i "$CONTAINER_NAME" tee /etc/containerd/certs.d/docker.io/hosts.toml > /dev/null << TOMLEOF
server = "https://registry-1.docker.io"

[host."http://${REGISTRY_ADDRESS}"]
  capabilities = ["pull", "resolve"]

[host."https://registry-1.docker.io"]
  capabilities = ["pull", "resolve"]
TOMLEOF
}

configure_guest_cdh_mirror() {
  log "Configuring guest CDH docker.io mirror -> $REGISTRY_ADDRESS (staged copy)"
  docker_exec "mkdir -p '$(dirname "$CDH_REGISTRY_CONFIG")'"
  "$CONTAINER_ENGINE" exec -i "$CONTAINER_NAME" tee "$CDH_REGISTRY_CONFIG" > /dev/null << TOMLEOF
unqualified-search-registries = ["docker.io"]

[[registry]]
location = "docker.io"

[[registry.mirror]]
location = "${REGISTRY_ADDRESS}"
insecure = true
TOMLEOF
}

# Returns 0 (true) if the initrd's baked-in etc/registry-configuration.toml
# already matches $CDH_REGISTRY_CONFIG.
initrd_already_patched() {
  docker_exec "
    set -e
    work=\$(mktemp -d)
    trap 'rm -rf \$work' EXIT
    cd \$work
    zcat '$LINUX_INITRD' 2>/dev/null | cpio -idmu --quiet
    diff -q etc/registry-configuration.toml '$CDH_REGISTRY_CONFIG' >/dev/null 2>&1
  "
}

repack_initrd_with_registry_mirror() {
  log "Baking registry mirror into guest initrd: $LINUX_INITRD"
  docker_exec "
set -euo pipefail
img='$LINUX_INITRD'
cfg='$CDH_REGISTRY_CONFIG'
backup=\"\${img}.bak-before-registry-mirror-\$(date +%Y%m%d%H%M%S)\"
cp -a \"\$img\" \"\$backup\"

work=\$(mktemp -d)
out=/tmp/kata-containers-initrd.img.registry-mirror
trap 'rm -rf \$work \$out' EXIT

cd \"\$work\"
zcat \"\$img\" 2>/dev/null | cpio -idmu --quiet
cp -a \"\$cfg\" etc/registry-configuration.toml
find . -print0 | cpio --null -o -H newc --quiet | gzip -9 > \"\$out\"
cp -a \"\$out\" \"\$img\"

echo \"Initrd backup: \$backup\"
ls -l \"\$img\"
"
}

configure_host_containerd_mirror
configure_guest_cdh_mirror

if initrd_already_patched; then
  log "Guest initrd already has the correct registry mirror, skipping repack."
else
  repack_initrd_with_registry_mirror
fi

log "Done. Remember to (re)start containerd so the host-side mirror config is picked up."
