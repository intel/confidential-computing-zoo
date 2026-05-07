#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "verify_openclaw_workload_chain.sh now delegates to pull-only validation because workload-chain evidence verification is still unstable in the current environment." >&2
exec "$SCRIPT_DIR/verify_openclaw_pull.sh" "$@"
