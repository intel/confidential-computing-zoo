#!/bin/bash

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

set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/common.sh"
tc_api_cd_repo_root

# TC API Development Setup Script

echo "Setting up TC API development environment..."

VENV_DIR="$TC_API_VENV_DIR"

check_python_version() {
	local python_bin="$1"
	"$python_bin" - <<'PY'
import sys

if sys.version_info < (3, 11):
	version = ".".join(str(part) for part in sys.version_info[:3])
	raise SystemExit(
		f"ERROR: tc-api requires Python >= 3.11, but found {version}. "
		"Set PYTHON_BIN=/usr/bin/python3.11 or run the script with python3.11 available first."
	)
PY
}

PYTHON_BIN="$(tc_api_find_python)" || {
	echo "ERROR: No Python 3 interpreter found. Install Python 3.11 and retry."
	exit 1
}

check_python_version "$PYTHON_BIN"

echo "Using Python interpreter: $PYTHON_BIN"

recreate_venv_if_needed() {
	if [[ ! -x "$VENV_DIR/bin/python" ]]; then
		return 0
	fi

	local current_version
	current_version="$($VENV_DIR/bin/python - <<'PY'
import sys
print(f"{sys.version_info[0]}.{sys.version_info[1]}")
PY
)"

	if [[ "$current_version" != "3.11" ]]; then
		echo "Removing existing virtual environment built with Python $current_version"
		rm -rf "$VENV_DIR"
	fi
}

#recreate_venv_if_needed

# Create virtual environment
"$PYTHON_BIN" -m venv "$VENV_DIR"

VENV_PYTHON="$VENV_DIR/bin/python"

# Install package and dependencies
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -e "$TC_API_REPO_ROOT/../tlog[rekor]" -e "$TC_API_REPO_ROOT"
"$VENV_PYTHON" -m pip install -r "$TC_API_REPO_ROOT/requirements-dev.txt"

# Create necessary directories
mkdir -p uploads builds logs

# Copy environment file
if [[ -f .env.example && ! -f .env ]]; then
	cp .env.example .env
fi

echo "Setup complete!"
echo ""
echo "Current local entrypoints:"
echo "1. Activate virtual environment: source $VENV_DIR/bin/activate"
echo "2. Start the full local stack: ./start.sh restart"
echo "3. For direct API-only development: python -m tc_api.api.app"
echo "4. Run tests: ./run_tests.sh --type all"
echo ""
echo "API will be available at: http://localhost:8000"
echo "API documentation: http://localhost:8000/docs"
