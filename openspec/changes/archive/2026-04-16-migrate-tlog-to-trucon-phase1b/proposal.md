## Why

Phase 1A migrated business endpoints from `ChainedTransparencyLog` to `TrustedLogAPI`, but left the legacy code in place and deferred full chain verification. The legacy `tlog_chain.py` and `/api/verify-tlog` endpoint are now dead code — nothing calls `ChainedTransparencyLog` in the hot path. Meanwhile, TruCon has no way to verify chain integrity beyond a lightweight head check. Phase 1B completes the migration by removing all legacy code and adding a full chain traversal verification endpoint to TruCon.

## What Changes

- **BREAKING**: Delete `tlog_chain.py` and all `ChainedTransparencyLog` references from the codebase
- **BREAKING**: Remove `/api/verify-tlog` endpoint and `verify_tlog()` method from `services.py`
- Clean up `trusted_container_log/__init__.py` to remove legacy exports
- Add `event_digest` column to TruCon's `commit_queue` SQLite table and persist it during `/commit`
- Add `GET /verify-chain/{chain_id}` endpoint to TruCon — full chain traversal with per-entry detailed results (sequence continuity, RTMR chain integrity, Rekor confirmation status)
- Update documentation to remove `ChainedTransparencyLog` references

## Capabilities

### New Capabilities
- `trucon-chain-verification`: Full chain traversal verification endpoint on TruCon (`GET /verify-chain/{chain_id}`) that checks sequence continuity, RTMR chain integrity via stored `event_digest`, and Rekor confirmation coverage. Returns detailed per-entry results.

### Modified Capabilities
- `tlog-chain-verification`: Remove legacy `ChainedTransparencyLog`-based verification requirements. The Rekor-level `verify_record()` remains unchanged; chain-level verification moves to TruCon.
- `tlog-audit-snapshot`: The commit receipt format is unchanged, but legacy file references in removal requirements are now enforced (files and code deleted, not just "no longer produced").

## Impact

- **`src/tc_api/trusted_container_log/tlog_chain.py`**: Deleted entirely
- **`src/tc_api/trusted_container_log/__init__.py`**: Remove `ChainedTransparencyLog` export
- **`src/tc_api/services.py`**: Remove `verify_tlog()` method and its local import
- **`src/tc_api/main.py`**: Remove `/api/verify-tlog` endpoint
- **`src/tc_api/trucon.py`**: Add `event_digest` column to `commit_queue`, add `/verify-chain/{chain_id}` endpoint
- **`docs/trusted-log/`**: Update references
