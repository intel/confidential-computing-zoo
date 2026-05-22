## Why

The architecture specifies a two-level digest algorithm: each entry is individually hashed, then the event digest is computed over the entry digests plus event metadata. The current implementation uses single-level hashing — raw entries are included directly in the predicate payload and a single SHA-384 pass covers everything. This means entry-level integrity cannot be independently verified, and the digest format diverges from the architecture spec (trusted-log/architecture.md §Digest Algorithm). This is a correctness fix tracked as FIX-01 in docs/overview_tasks.md.

## What Changes

- Add two module-level helper functions in `tlog_client.py`: `compute_entry_digest(key, value)` and `compute_event_digest(event_id, event_type, created_iso, entry_digests)`.
- Refactor `commit_record()` to compute per-entry SHA-384 digests first, then compute event digest from `{event_id, event_type, created, [entry_digests]}`.
- The DSSE predicate payload will include **both** raw `entries` (for auditing) and `entry_digests` (for verification), plus the final `digest`.
- No backward compatibility for existing records — old digest format in existing DB rows is accepted as-is by `/verify-chain` (which only compares stored `event_digest` against RTMR chain, never recomputes from entries).
- No changes to TruCon server (`trucon/app.py`, `trucon/database.py`); only the digest producer (`tlog_client.py`) changes.

## Capabilities

### New Capabilities
- `trucon-two-level-digest`: Two-level (entry + event) digest computation per architecture spec, with `compute_entry_digest` and `compute_event_digest` helpers.

### Modified Capabilities
- `tlog-rest-commit`: The DSSE predicate format changes — `entry_digests` array added alongside existing `entries`, and digest computation switches to two-level algorithm.

## Impact

- **Code**: `src/tc_api/tlog_client.py` — `commit_record()` refactored, two new module functions added.
- **Wire format**: DSSE predicate gains `entry_digests` field. Consumers that parse the predicate should handle the new field.
- **Tests**: New unit tests for digest helpers and end-to-end predicate verification. Existing tests use mock digests and should not break.
- **No DB migration**: `event_digest` column format unchanged (`sha384:<hex>`). Old records remain valid.
