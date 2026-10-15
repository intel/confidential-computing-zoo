#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ $# == 1 ]] || { echo "usage: build.sh /absolute/clean/trustee-checkout" >&2; exit 1; }
SOURCE="$(cd "$1" && pwd)"
[[ "$(uname -s)" == Linux ]] || { echo "Trustee build requires Linux" >&2; exit 1; }
[[ -z "$(git -C "$SOURCE" status --porcelain)" ]] || { echo "use a clean Trustee checkout" >&2; exit 1; }
# The hook is reviewed against this upstream source; apply.py also checks the
# source-file hash before changing the Quote/appraisal integration point.
[[ "$(git -C "$SOURCE" describe --tags --exact-match)" == v0.21.0 ]] || { echo "expected reviewed upstream tag v0.21.0" >&2; exit 1; }
python3 "$HERE/apply.py" "$SOURCE"
(cd "$SOURCE" && cargo build --locked --release -p attestation-service --no-default-features --features restful-bin,tdx-verifier)
printf 'TRUSTEE_BUILD=PASS\nBINARY=%s/target/release/restful-as\n' "$SOURCE"
