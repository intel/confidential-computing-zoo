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

from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, Optional


def ensure_docktap_authorization(
    base_url: str,
    chain_id: Optional[str] = None,
    *,
    identity_token: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    payload = {}
    if chain_id:
        payload["chain_id"] = chain_id
    if identity_token:
        payload["identity_token"] = identity_token

    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/docktap/authorize",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        summary = json.loads(response.read().decode("utf-8"))

    if summary.get("ready"):
        return summary

    detail = summary.get("detail") or summary.get("source") or "authorization readiness failed"
    raise RuntimeError(f"Docktap authorization not ready: {detail}")