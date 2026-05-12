#!/bin/bash

set -euo pipefail

# TC API Development Setup Script

echo "Setting up TC API development environment..."

VENV_DIR="venv"

find_python() {
	if [[ -n "${PYTHON_BIN:-}" ]]; then
		echo "$PYTHON_BIN"
		return 0
	fi

	if command -v python3.11 >/dev/null 2>&1; then
		echo "python3.11"
		return 0
	fi

	if command -v python3 >/dev/null 2>&1; then
		echo "python3"
		return 0
	fi

	return 1
}

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

PYTHON_BIN="$(find_python)" || {
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

recreate_venv_if_needed

# Create virtual environment
"$PYTHON_BIN" -m venv "$VENV_DIR"

VENV_PYTHON="$VENV_DIR/bin/python"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install package and dependencies
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -e "$SCRIPT_DIR/../tlog" -e "$SCRIPT_DIR/../tlog-rekor" -e .

# Create necessary directories
mkdir -p uploads builds logs

# Copy environment file
if [[ -f .env.example && ! -f .env ]]; then
	cp .env.example .env
fi

echo "Setup complete!"
echo ""
echo "To run the service:"
echo "1. Activate virtual environment: source $VENV_DIR/bin/activate"
echo "2. Start the service: python -m tc_api.main"
echo ""
echo "API will be available at: http://localhost:8000"
echo "API documentation: http://localhost:8000/docs"
