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

# Backward-compatible wrapper for the single Python test entrypoint.
set -e

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/common.sh"

tc_api_cd_repo_root
tc_api_activate_venv_if_present
tc_api_prepend_repo_root_to_pythonpath
PYTHON_BIN="$(tc_api_default_python_bin)"
export TRUCON_AUTH_DISABLED=true

"$PYTHON_BIN" -m tests.test_runner "$@"
