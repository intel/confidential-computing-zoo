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

import json
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from sigstore.dsse import StatementBuilder, Subject
from tlog.digest import compute_entry_digest, compute_event_digest
from tlog.types import Entry

from ..trucon.owner_authorization import sign_owner_authorization


PREDICATE_TYPE = "https://trusted-log.dev/v1"


def build_event_predicate(entries: Iterable[Entry], *, event_id: str, event_type: str, created_iso: Optional[str] = None) -> tuple[Dict[str, Any], str]:
    entry_list = list(entries)
    created = created_iso or datetime.utcnow().isoformat()
    entry_digests = [compute_entry_digest(entry.key, entry.value) for entry in entry_list]
    event_digest = compute_event_digest(event_id, event_type, created, entry_digests)
    predicate_payload = {
        "event_id": event_id,
        "event_type": event_type,
        "created": created,
        "entries": [{"key": entry.key, "value": entry.value} for entry in entry_list],
        "entry_digests": entry_digests,
        "digest": event_digest,
    }
    return predicate_payload, event_digest


def attach_commit_context(
    predicate_payload: Dict[str, Any],
    *,
    chain_id: str,
    reservation: Dict[str, Any],
    event_digest: str,
    owner_private_key: Any = None,
    delegation_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    predicate_payload["chain_id"] = chain_id
    predicate_payload["sequence_num"] = reservation["sequence_num"]
    predicate_payload["prev_event_digest"] = reservation.get("prev_event_digest")
    predicate_payload["prev_lookup_hash"] = reservation.get("prev_lookup_hash")
    if delegation_id is not None:
        predicate_payload["delegation_id"] = delegation_id

    if owner_private_key is None:
        return None

    owner_authorization = sign_owner_authorization(
        private_key=owner_private_key,
        chain_id=chain_id,
        sequence_num=reservation["sequence_num"],
        prev_event_digest=reservation.get("prev_event_digest"),
        prev_lookup_hash=reservation.get("prev_lookup_hash"),
        event_digest=event_digest,
    )
    predicate_payload["owner_authorization"] = owner_authorization
    return owner_authorization


def build_statement(chain_id: str, event_digest: str, predicate_payload: Dict[str, Any]):
    subject = Subject(
        name=f"trusted-log-chain_{chain_id}",
        digest={"sha384": event_digest.split(":")[1]},
    )
    return (
        StatementBuilder()
        .subjects([subject])
        .predicate_type(PREDICATE_TYPE)
        .predicate(predicate_payload)
        .build()
    )


def build_statement_json(chain_id: str, event_digest: str, predicate_payload: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "_type": "https://in-toto.io/Statement/v0.1",
            "subject": [
                {
                    "name": f"trusted-log-chain_{chain_id}",
                    "digest": {"sha384": event_digest.split(":")[1]},
                }
            ],
            "predicateType": PREDICATE_TYPE,
            "predicate": predicate_payload,
        }
    )