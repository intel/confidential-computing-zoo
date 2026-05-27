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