#!/usr/bin/env bash
set -euo pipefail
WORKLOAD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPIRE_ROOT="$(dirname "$WORKLOAD_ROOT")"
OUT="${ARGUS_WORKLOAD_BUILD_DIR:-$WORKLOAD_ROOT/build}"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || { echo "TDX build requires Linux x86_64" >&2; exit 1; }
mkdir -p "$OUT/bin"
OUT="$(cd "$OUT" && pwd)"
# Remove success metadata first so a later build failure cannot leave an older
# receipt that appears to describe the partially refreshed output directory.
rm -f -- "$OUT/SHA256SUMS" "$OUT/SHA256SUMS.tmp" "$OUT/build-manifest.json"
source "$WORKLOAD_ROOT/scripts/build-artifacts.sh"
(cd "$SPIRE_ROOT/plugins/argus-tdx-nodeattestor" && go build -mod=readonly -trimpath -o "$OUT/bin/argus-tdx-nodeattestor-agent" ./cmd/agent && go build -mod=readonly -trimpath -o "$OUT/bin/argus-tdx-nodeattestor-server" ./cmd/server)
(cd "$SPIRE_ROOT/plugins/argus-tdx-workloadattestor" && go build -mod=readonly -trimpath -o "$OUT/bin/argus-tdx-workloadattestor" ./cmd/argus-tdx-workloadattestor)
(cd "$WORKLOAD_ROOT" && go build -mod=readonly -trimpath -o "$OUT/bin/argus-workload" ./cmd/argus-workload)
(cd "$SPIRE_ROOT/helpers/spiffe-helper" && go build -mod=readonly -trimpath -ldflags '-X github.com/spiffe/spiffe-helper/pkg/version.gittag=argus-broker' -o "$OUT/bin/spiffe-helper" ./cmd/spiffe-helper)
for tool in argus-agent-config spiffe-authz spiffe-mtls-probe; do
    (cd "$SPIRE_ROOT/helpers/spiffe-helper" && go build -mod=readonly -trimpath -o "$OUT/bin/$tool" "./cmd/$tool")
done
(export CARGO_TARGET_DIR="$OUT/cargo-provider"; cd "$SPIRE_ROOT/../argus" && cargo build --locked --release --bin argus-spire-evidence-provider)
install -m 0755 "$OUT/cargo-provider/release/argus-spire-evidence-provider" "$OUT/bin/"
archive="$OUT/spire-1.15.3-linux-amd64-musl.tar.gz"
# Use the reviewed official SPIRE payload; verify its archive before extraction.
curl --fail --location --retry 3 --proto '=https' --tlsv1.2 https://github.com/spiffe/spire/releases/download/v1.15.3/spire-1.15.3-linux-amd64-musl.tar.gz -o "$archive"
printf 'ca1a4d1155317bdd2afc7f36663828a10410c7c840e54725b90b4064b0a301c7  %s\n' "$archive" | sha256sum --check
tar -xzf "$archive" -C "$OUT"
[[ "$("$OUT/spire-1.15.3/bin/spire-agent" -version 2>&1)" == 1.15.3 ]]
[[ "$("$OUT/spire-1.15.3/bin/spire-server" -version 2>&1)" == 1.15.3 ]]
python3 "$WORKLOAD_ROOT/scripts/build_manifest.py" create --root "$WORKLOAD_ROOT" --output "$OUT" "${ARGUS_WORKLOAD_ARTIFACTS[@]}"
# Publish the complete checksum list only after every artifact and manifest exists.
(cd "$OUT" && sha256sum -- "${ARGUS_WORKLOAD_ARTIFACTS[@]}" > SHA256SUMS.tmp && mv -f -- SHA256SUMS.tmp SHA256SUMS)
printf 'BUILD=PASS\nOUTPUT=%s\n' "$OUT"
