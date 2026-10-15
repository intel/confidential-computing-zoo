#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ARGUS_WORKLOAD_BUILD_DIR:-$ROOT/build}"
[[ "$EUID" == 0 ]] || { echo "run install as root" >&2; exit 1; }
[[ "$#" == 2 && "$1" == --config ]] || { echo "usage: install.sh --config /absolute/environment.json" >&2; exit 1; }
INPUT="$2"
settings="$(python3 "$ROOT/scripts/deployment.py" paths --config "$INPUT")"
mapfile -t paths <<< "$settings"
INSTALL_DIR="${paths[0]}"
CONFIG_DIR="${paths[1]}"
RECORDS_DIR="${paths[2]}"
SPIRE_DIR="${paths[3]}"
RUN_DIR="${paths[4]}"
[[ -f "$OUT/SHA256SUMS" ]] || { echo "run build.sh first" >&2; exit 1; }
source "$ROOT/scripts/build-artifacts.sh"
for artifact in "${ARGUS_WORKLOAD_ARTIFACTS[@]}"; do
    [[ -f "$OUT/$artifact" && -x "$OUT/$artifact" ]] || { echo "missing executable build artifact: $artifact; run build.sh first" >&2; exit 1; }
done
# Compare the complete current payload, including official SPIRE executables.
# An older or incomplete manifest cannot authorize a newer, unlisted binary.
expected_checksums="$(cd "$OUT" && sha256sum -- "${ARGUS_WORKLOAD_ARTIFACTS[@]}")"
[[ "$(cat "$OUT/SHA256SUMS")" == "$expected_checksums" ]] || { echo "build manifest is stale, incomplete, or contains changed artifacts; run build.sh first" >&2; exit 1; }
python3 "$ROOT/scripts/build_manifest.py" verify --root "$ROOT" --output "$OUT" "${ARGUS_WORKLOAD_ARTIFACTS[@]}"
for tool in python3 nginx nsenter docker systemctl openssl timeout; do
    command -v "$tool" >/dev/null || { echo "missing command: $tool" >&2; exit 1; }
done
nginx -V 2>&1 | grep -q -- --with-http_auth_request_module || { echo "NGINX auth_request module required" >&2; exit 1; }
unit_names="$(python3 "$ROOT/scripts/deployment.py" units --config "$INPUT")"
# Replacing binaries/configuration under active services could mix generations.
for unit in $unit_names; do
    state="$(systemctl is-active "$unit" || true)"
    case "$state" in
        active|activating|reloading|deactivating) echo "stop $unit before installing deployment configuration" >&2; exit 1 ;;
    esac
done
getent group argus-nginx >/dev/null || groupadd --system argus-nginx
id argus-nginx >/dev/null 2>&1 || useradd --system --gid argus-nginx --no-create-home --shell /usr/sbin/nologin argus-nginx
install -d -m 0755 "$INSTALL_DIR/bin" "$INSTALL_DIR/scripts" "$INSTALL_DIR/config" "$INSTALL_DIR/policy" "$INSTALL_DIR/systemd" "$SPIRE_DIR"
install -d -m 0700 "$CONFIG_DIR" "$RUN_DIR" "$RECORDS_DIR"
install -m 0644 "$OUT/build-manifest.json" "$OUT/SHA256SUMS" "$INSTALL_DIR/"
for artifact in "${ARGUS_WORKLOAD_ARTIFACTS[@]}"; do
    case "$artifact" in
        bin/*) install -m 0755 "$OUT/$artifact" "$INSTALL_DIR/bin/" ;;
        spire-1.15.3/bin/*) install -m 0755 "$OUT/$artifact" "$SPIRE_DIR/" ;;
    esac
done
install -m 0755 "$ROOT"/scripts/*.py "$INSTALL_DIR/scripts/"
install -m 0644 "$ROOT/scripts/nginx-hook.sh" "$INSTALL_DIR/scripts/"
install -m 0644 "$ROOT"/config/* "$INSTALL_DIR/config/"
install -m 0644 "$ROOT"/policy/* "$INSTALL_DIR/policy/"
install -m 0644 "$ROOT"/systemd/* "$INSTALL_DIR/systemd/"
python3 "$ROOT/scripts/deployment.py" render-services --config "$INPUT"
install -m 0644 "$CONFIG_DIR"/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
# Installation renders units but does not start or attest a workload. The
# lifecycle commands perform launch association, registration and preflight.
printf 'INSTALL=PASS\nCONFIG=%s/environment.json\n' "$CONFIG_DIR"
