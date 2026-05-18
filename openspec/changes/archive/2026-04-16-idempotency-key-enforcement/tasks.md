## 1. Schema and Database Layer

- [x] 1.1 Add `idempotency_key TEXT UNIQUE` column to `CREATE TABLE commit_queue` in `src/tc_api/trucon/database.py`
- [x] 1.2 Add `'idempotency_key': 'TEXT UNIQUE'` to the legacy migration dict in `_migrate_legacy_schema()`
- [x] 1.3 Add `idempotency_key: Optional[str] = None` parameter to `insert_record()` and include it in the INSERT statement
- [x] 1.4 Add `get_record_by_idempotency_key(idempotency_key, chain_id, db_path)` query function that returns the matching row or None

## 2. TruCon Commit Endpoint

- [x] 2.1 Add `idempotency_key: Optional[str] = None` field to `CommitRequest` model in `src/tc_api/trucon/app.py`
- [x] 2.2 Inside `_sequencer_lock` in the `/commit` handler, add idempotency check before RTMR extend: if key is provided and a matching record exists, return cached `CommitResponse` from existing record data
- [x] 2.3 Pass `idempotency_key` to `insert_record()` call within the lock body

## 3. tc_api Client Side

- [x] 3.1 In `TrustedLogAPI.commit_record()` in `src/tc_api/tlog_client.py`, generate `idk-<uuid-hex-12>` key (or take from `commit_options["idempotency_key"]`) before signing
- [x] 3.2 Add `idempotency_key` parameter to `_post_to_trucon()` and include it in the JSON payload
- [x] 3.3 Pass the generated key from `commit_record()` through to `_post_to_trucon()`

## 4. Tests

- [x] 4.1 Test: `insert_record` with `idempotency_key` stores and retrieves correctly via `get_record_by_idempotency_key`
- [x] 4.2 Test: duplicate `idempotency_key` INSERT raises `IntegrityError` (UNIQUE constraint)
- [x] 4.3 Test: `/commit` with idempotency key — first request succeeds, second returns same `record_id` and `sequence_num` without RTMR extend
- [x] 4.4 Test: `/commit` duplicate matching FAILED record returns FAILED data
- [x] 4.5 Test: `/commit` without idempotency key proceeds normally (backward compat)
- [x] 4.6 Test: schema migration adds `idempotency_key` column to legacy table
- [x] 4.7 Test: `commit_record()` generates idempotency key and includes it in TruCon payload
