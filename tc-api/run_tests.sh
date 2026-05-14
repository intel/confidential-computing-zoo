#!/bin/bash

# Backward-compatible wrapper for the single Python test entrypoint.
set -e

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/common.sh"

tc_api_cd_repo_root
tc_api_activate_venv_if_present
tc_api_prepend_src_to_pythonpath
PYTHON_BIN="$(tc_api_default_python_bin)"
export TRUCON_AUTH_DISABLED=true

"$PYTHON_BIN" -m tests.test_runner "$@"
