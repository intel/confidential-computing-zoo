## 1. Digest Helper Functions

- [x] 1.1 Add `compute_entry_digest(key: str, value: str) -> str` module-level function in `tlog_client.py` — returns `"sha384:<hex>"` using `canonical_json({"key": key, "value": value})`
- [x] 1.2 Add `compute_event_digest(event_id: str, event_type: str, created_iso: str, entry_digests: list[str]) -> str` module-level function in `tlog_client.py` — returns `"sha384:<hex>"` using `canonical_json({"created": ..., "entry_digests": [...], "event_id": ..., "event_type": ...})`

## 2. Refactor commit_record()

- [x] 2.1 In `commit_record()`, compute `entry_digests` list by calling `compute_entry_digest()` for each entry
- [x] 2.2 Replace single-level digest computation with `compute_event_digest()` call
- [x] 2.3 Add `entry_digests` field to `predicate_payload` alongside existing `entries`
- [x] 2.4 Verify `digest` field in predicate is set from `compute_event_digest()` return value

## 3. Tests

- [x] 3.1 Unit test: `compute_entry_digest` returns deterministic `"sha384:<hex>"` for given key/value
- [x] 3.2 Unit test: `compute_event_digest` returns deterministic `"sha384:<hex>"` for given inputs
- [x] 3.3 Unit test: entry order sensitivity — swapped entries produce different event digest
- [x] 3.4 Unit test: empty entries list produces valid event digest
- [x] 3.5 Unit test: two-level digest differs from single-level digest for same entries
- [x] 3.6 Integration test: `commit_record()` predicate contains `entries`, `entry_digests`, and `digest` keys, with `digest` matching `compute_event_digest()` output

## 4. Regression Validation

- [x] 4.1 Run existing test suites (`test_sequencer_refactor.py`, `test_tlog_refactored.py`, `test_idempotency.py`) and confirm zero regressions
