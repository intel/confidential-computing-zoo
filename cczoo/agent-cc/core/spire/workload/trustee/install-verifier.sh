#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TLOG="$(cd "$HERE/../../.." && pwd)/tlog"
[[ "$EUID" == 0 && $# == 1 && "$1" == /* ]] || { echo "usage (root): install-verifier.sh /absolute/install-directory" >&2; exit 1; }
DEST="$1"
[[ "$DEST" =~ ^/[A-Za-z0-9_/-]+$ && "$DEST" != / && ! -e "$DEST" ]] || { echo "use a new dedicated directory" >&2; exit 1; }
install -d -m 0755 "$DEST"
python3 -m venv "$DEST/venv"
"$DEST/venv/bin/python" -m pip install -r "$HERE/requirements.txt" "$TLOG"
install -m 0644 "$HERE/verify_trucon.py" "$DEST/verify_trucon.py"
# Isolated Python uses the installed venv packages, ignoring PYTHONPATH and the
# caller's working directory when the AS launches the verifier.
printf '#!/bin/sh\nexec "%s/venv/bin/python" -I "%s/verify_trucon.py" "$@"\n' "$DEST" "$DEST" > "$DEST/verify-trucon"
chmod 0755 "$DEST/verify-trucon"
printf 'VERIFIER=%s/verify-trucon\n' "$DEST"
