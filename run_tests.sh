#!/bin/bash

# Backward-compatible wrapper for the single Python test entrypoint.
set -e

if [ -d "venv" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

python test_runner.py "$@"
