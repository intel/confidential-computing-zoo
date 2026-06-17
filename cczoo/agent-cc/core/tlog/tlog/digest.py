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

import hashlib
import json
from typing import Any, List


def canonical_json(data: Any) -> str:
    """Return a highly deterministic JSON serialization for hashing."""
    return json.dumps(data, separators=(',', ':'), sort_keys=True, ensure_ascii=False)


def compute_entry_digest(key: str, value: Any) -> str:
    """Compute SHA-384 digest of a single entry: SHA384(canonical({"key": k, "value": v}))."""
    payload = canonical_json({"key": key, "value": value})
    return "sha384:" + hashlib.sha384(payload.encode("utf-8")).hexdigest()


def compute_event_digest(event_id: str, event_type: str, created_iso: str, entry_digests: List[str]) -> str:
    """Compute SHA-384 event digest over metadata + entry digests (two-level algorithm)."""
    payload = canonical_json({
        "created": created_iso,
        "entry_digests": entry_digests,
        "event_id": event_id,
        "event_type": event_type,
    })
    return "sha384:" + hashlib.sha384(payload.encode("utf-8")).hexdigest()
