## Why

The current `TrustedLogAPI` class holds all chain state (`_records`, `_entries`, `_latest_confirmed_log_id`) in process-local memory and performs RTMR extend + SQLite INSERT as separate, non-atomic steps inside `commit_record()`. When `tc_api` runs with `uvicorn --workers 4`, each worker fork gets an independent copy of this state, producing six critical concurrency bugs: siloed in-memory state across workers, RTMR extend race conditions (no cross-process locking), non-atomic insert+extend leaving inconsistent hardware/queue state on crash, daemon/worker double-submit to Rekor, broken `prev_log_id` chain tracking, and duplicate daemon instances. Additionally, embedding `prev_log_id` inside the DSSE predicate creates a three-way contradiction: the API caller signs before the system can assign the correct `prev_log_id`, yet the field must be cryptographically bound.

## What Changes

- **BREAKING**: Split `TrustedLogAPI` into two services: a stateless **tc_api** (multi-worker safe) and a single-instance **Trust API** process that serializes all chain-mutating operations.
- **BREAKING**: Remove `prev_log_id` from the DSSE predicate payload. The system maintains `prev_log_id` internally in SQLite; ordering is proven by the RTMR hardware chain, not by the signature.
- Trust API serializes RTMR extend + SQLite INSERT behind a `threading.Lock()`, making the commit path atomic within the single process.
- Trust API embeds the submit daemon as a background thread (replacing the standalone `tlog_daemon.py` process), draining the queue to Rekor in `sequence_num` order.
- tc_api performs Sigstore DSSE signing locally, then sends the signed bundle to Trust API via REST for sequencing.
- Expand `commit_queue` table with `rtmr_extended`, `log_id`, `prev_log_id`, `mr_value`, `sequence_num`, and `confirmed_at` fields. Add a `chain_state` table for persistent chain head tracking.
- Crash recovery uses `rtmr_extended` flag: on restart, records with `rtmr_extended=TRUE` but not yet confirmed in Rekor resume submission; records with `rtmr_extended=FALSE` are discarded (RTMR reset invalidates them).
- Verification uses `chain_id` (from DSSE predicate) + signer identity filtering when searching Rekor, mitigating injection attacks.
- Single-instance enforcement for Trust API via file lock or PID check.
- Records that exceed 10 retries move to `FAILED` status; `FAILED` records block subsequent Rekor submissions but do not block RTMR extends for new commits.

## Capabilities

### New Capabilities
- `tlog-sequencer`: Single-instance Trust API service that serializes RTMR extend and SQLite INSERT behind a lock, maintains chain state, and enforces single-process operation.
- `tlog-rest-commit`: REST API contract between tc_api and Trust API for the commit flow — tc_api signs the DSSE envelope, Trust API sequences it (RTMR extend + queue insert + chain state update).
- `tlog-embedded-submitter`: Background thread inside Trust API that drains the commit queue to Rekor in sequence order, with retry counting, failure thresholds, and ordered delivery guarantees.
- `tlog-chain-verification`: Verification flow using chain_id and signer identity filtering for Rekor log entry retrieval, with RTMR quote cross-checking for ordering proof.

### Modified Capabilities
- `trusted-log-sqlite-queue`: Schema expansion with new columns (`rtmr_extended`, `log_id`, `prev_log_id`, `mr_value`, `sequence_num`, `confirmed_at`) and new `chain_state` table. Crash recovery logic changes from unconditional discard to conditional recovery based on `rtmr_extended` flag.

## Impact

- **Code**: `trusted_container_log/api.py` split into two modules (tc_api-side committer, Trust API-side sequencer). `tlog_daemon.py` removed and replaced by embedded thread. `trusted_container_log/database.py` schema expanded. `main.py` commit endpoint changes from local `TrustedLogAPI` call to REST call to Trust API.
- **APIs**: New internal REST endpoints on Trust API (`POST /commit`, `GET /status`, `GET /chain-state`). tc_api public API surface unchanged for callers.
- **Deployment**: `docker-compose.yml` replaces `tlog-daemon` service with `trust-api` service. `start.sh` updated. Trust API must run `--workers 1`.
- **Dependencies**: No new external dependencies. `sigstore-python`, `sqlite3`, `threading` remain.
- **Trust Model**: Three-layer proof — DSSE proves event authenticity, RTMR proves ordering, Rekor proves public auditability. `prev_log_id` no longer in the signed envelope (breaking change for verifiers expecting it).
