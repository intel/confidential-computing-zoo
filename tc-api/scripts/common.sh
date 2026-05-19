#!/bin/bash

TC_API_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TC_API_REPO_ROOT="$(cd "$TC_API_COMMON_DIR/.." && pwd)"
TC_API_VENV_DIR="$TC_API_REPO_ROOT/venv"

tc_api_cd_repo_root() {
	cd "$TC_API_REPO_ROOT"
}

tc_api_activate_venv_if_present() {
	if [[ -x "$TC_API_VENV_DIR/bin/activate" ]]; then
		# shellcheck disable=SC1091
		source "$TC_API_VENV_DIR/bin/activate"
	fi
}

tc_api_prepend_repo_root_to_pythonpath() {
	export PYTHONPATH="$TC_API_REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
}

tc_api_default_python_bin() {
	if [[ -n "${PYTHON_BIN:-}" ]]; then
		echo "$PYTHON_BIN"
	elif [[ -x "$TC_API_VENV_DIR/bin/python" ]]; then
		echo "$TC_API_VENV_DIR/bin/python"
	else
		echo "python3"
	fi
}

tc_api_find_python() {
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