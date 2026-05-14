import hashlib
import json
import logging
import os
import threading
import uuid
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import urllib.error

from cryptography import x509
from cryptography.x509.oid import NameOID
from sigstore.sign import SigningContext
from sigstore.oidc import IdentityToken
from sigstore.dsse import StatementBuilder, Subject
from sigstore.models import Bundle

from ..identity.sigstore_baseline import build_baseline_sigstore_bundle, build_signing_context
from ..identity.sigstore_baseline import get_chain_owner_private_key
from ..trucon.owner_authorization import sign_owner_authorization, verify_owner_authorization
from tlog.types import (
    RecordContext, Entry, Record, EventLog, CommitResult,
    CommitQueueStatus, LatestState, VerificationResult, SubmitStatus
)
from tlog.errors import RecordNotFoundError, BackendSubmitError, VerificationError
from ..trucon.database import get_chain_state
from ..trucon.internal_transport import request_json

from tlog.digest import canonical_json, compute_entry_digest, compute_event_digest

logger = logging.getLogger(__name__)



def _entry_has_required_history_fields(entry: Dict[str, Any]) -> bool:
    return all(
        entry.get(field) is not None
        for field in ("event_id", "event_type", "sequence_num", "digest")
    )
def _entry_has_event_log0_baseline(entry: Dict[str, Any]) -> bool:
    if entry.get("event_type") != "chain.init":
        return True
    observed = {
        item.get("key")
        for item in entry.get("predicate_entries", [])
        if isinstance(item, dict)
    }
    return {"baseline_rtmr", "pub_key"}.issubset(observed) and (
        "ccel_eventlog_b64" in observed or "ccel_digest" in observed
    )
def _predicate_entry_value(predicate_entries: List[Dict[str, Any]], key: str) -> Optional[str]:
    for entry in predicate_entries:
        if isinstance(entry, dict) and entry.get("key") == key:
            value = entry.get("value")
            return value if isinstance(value, str) else None
    return None
def _replay_owner_pub_key(entries: List[Dict[str, Any]]) -> Optional[str]:
    ordered = sorted(
        entries,
        key=lambda entry: (
            not isinstance(entry.get("sequence_num"), int),
            entry.get("sequence_num") if isinstance(entry.get("sequence_num"), int) else 1 << 30,
        ),
    )
    for entry in ordered:
        if entry.get("event_type") != "chain.init":
            continue
        return _predicate_entry_value(entry.get("predicate_entries", []), "pub_key")
    return None
__all__ = ['_entry_has_required_history_fields', '_entry_has_event_log0_baseline', '_predicate_entry_value', '_replay_owner_pub_key']
