#!/bin/bash

# Backward-compatible wrapper for the single Python test entrypoint.
set -e

if [ -d "venv" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

python -m tests.test_runner "$@"
