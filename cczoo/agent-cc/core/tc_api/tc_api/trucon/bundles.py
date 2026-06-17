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

import base64
import hashlib
import json
from typing import Any, Dict, Optional

from sigstore.models import Bundle


def extract_bundle_payload(bundle_json: str) -> Dict[str, Any]:
    parsed = json.loads(bundle_json)
    if isinstance(parsed, dict) and parsed.get("_owner_key_signed"):
        envelope = parsed.get("envelope", {})
        payload_b64 = envelope.get("payload")
        if not isinstance(payload_b64, str):
            raise ValueError("Owner-key-signed bundle missing payload")
        return json.loads(base64.b64decode(payload_b64).decode("utf-8"))

    bundle = Bundle.from_json(bundle_json)
    envelope = bundle._dsse_envelope
    if envelope is None:
        raise ValueError("Bundle does not contain a DSSE envelope")
    envelope_json = json.loads(envelope.to_json())
    payload_b64 = envelope_json.get("payload")
    if not isinstance(payload_b64, str):
        raise ValueError("Bundle DSSE envelope is missing payload")
    return json.loads(base64.b64decode(payload_b64).decode("utf-8"))


def extract_bundle_predicate(bundle_json: str) -> Dict[str, Any]:
    payload = extract_bundle_payload(bundle_json)
    predicate = payload.get("predicate")
    if not isinstance(predicate, dict):
        raise ValueError("Bundle DSSE payload is missing predicate")
    return predicate


def get_predicate_operation_type(predicate: Dict[str, Any]) -> Optional[str]:
    event_type = predicate.get("event_type")
    if isinstance(event_type, str):
        if event_type == "build" or event_type.endswith("_build"):
            return "build"

    entries = predicate.get("entries")
    if not isinstance(entries, list):
        return None

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("key") != "operation_type":
            continue
        value = entry.get("value")
        if isinstance(value, str):
            return value
    return None


def should_extend_rtmr(predicate: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(predicate, dict):
        return True
    return get_predicate_operation_type(predicate) != "build"


def compute_bundle_payload_hash(bundle_json: str) -> str:
    parsed = json.loads(bundle_json)
    if isinstance(parsed, dict) and parsed.get("_owner_key_signed"):
        envelope = parsed.get("envelope", {})
        payload_b64 = envelope.get("payload")
        if not isinstance(payload_b64, str):
            raise ValueError("Owner-key-signed bundle missing payload")
        payload_bytes = base64.b64decode(payload_b64)
        return "sha256:" + hashlib.sha256(payload_bytes).hexdigest()

    payload_bytes = base64.b64decode(extract_bundle_payload_b64(bundle_json))
    return "sha256:" + hashlib.sha256(payload_bytes).hexdigest()


def compute_record_lookup_hash(record: Any) -> Optional[str]:
    payload = record["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        return None
    bundle_json = payload.get("bundle")
    if not isinstance(bundle_json, str):
        return None
    try:
        return compute_bundle_payload_hash(bundle_json)
    except Exception:
        return None


def extract_bundle_payload_b64(bundle_json: str) -> str:
    parsed = json.loads(bundle_json)
    if isinstance(parsed, dict) and parsed.get("_owner_key_signed"):
        envelope = parsed.get("envelope", {})
        payload_b64 = envelope.get("payload")
        if not isinstance(payload_b64, str) or not payload_b64:
            raise ValueError("Owner-key-signed bundle missing payload")
        return payload_b64

    bundle = Bundle.from_json(bundle_json)
    envelope = bundle._dsse_envelope
    if envelope is None:
        raise ValueError("Bundle does not contain a DSSE envelope")
    envelope_json = json.loads(envelope.to_json())
    payload_b64 = envelope_json.get("payload")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise ValueError("Bundle DSSE envelope is missing payload")
    return payload_b64
