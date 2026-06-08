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

"""Delegation event predicate builder and helpers."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from tlog.digest import (
    compute_entry_digest,
    compute_event_digest,
)
from ..trucon.owner_authorization import sign_owner_authorization
from ..identity.sigstore_baseline import get_chain_owner_private_key
from .config import (
    DELEGATION_TTL_SECONDS as DOCKTAP_DELEGATION_TTL_SECONDS,
    delegation_scope,
)

DEFAULT_SCOPE = delegation_scope()


def build_delegation_predicate(
    chain_id: str,
    sequence_num: int,
    prev_event_digest: Optional[str],
    prev_lookup_hash: Optional[str],
    scope: Optional[List[str]] = None,
    ttl_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a delegation event predicate dict.

    Returns (predicate_payload, event_digest, delegation_id, expires_at_iso).
    """
    delegation_id = f"del-{uuid.uuid4().hex[:12]}"
    ttl = ttl_seconds if ttl_seconds is not None else DOCKTAP_DELEGATION_TTL_SECONDS
    created_iso = datetime.now(timezone.utc).isoformat()
    expires_at_iso = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()
    resolved_scope = scope if scope is not None else delegation_scope()

    event_id = f"evt-del-{uuid.uuid4().hex[:8]}"
    event_type = "session.delegation"

    entries = [
        {"key": "delegation_id", "value": delegation_id},
        {"key": "scope", "value": ",".join(resolved_scope)},
        {"key": "expires_at", "value": expires_at_iso},
    ]
    entry_digests = [compute_entry_digest(e["key"], e["value"]) for e in entries]
    event_digest = compute_event_digest(event_id, event_type, created_iso, entry_digests)

    predicate_payload: Dict[str, Any] = {
        "event_id": event_id,
        "event_type": event_type,
        "created": created_iso,
        "entries": entries,
        "entry_digests": entry_digests,
        "digest": event_digest,
        "chain_id": chain_id,
        "sequence_num": sequence_num,
        "prev_event_digest": prev_event_digest,
        "prev_lookup_hash": prev_lookup_hash,
        "delegation_id": delegation_id,
        "scope": resolved_scope,
        "expires_at": expires_at_iso,
    }

    # Add owner_authorization
    owner_private_key = get_chain_owner_private_key(chain_id)
    if owner_private_key is not None:
        owner_auth = sign_owner_authorization(
            private_key=owner_private_key,
            chain_id=chain_id,
            sequence_num=sequence_num,
            prev_event_digest=prev_event_digest,
            prev_lookup_hash=prev_lookup_hash,
            event_digest=event_digest,
        )
        predicate_payload["owner_authorization"] = owner_auth

    return predicate_payload, event_digest, delegation_id, expires_at_iso
