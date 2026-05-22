## 1. Database Schema Expansion

- [x] 1.1 Add new columns to `commit_queue` table: `chain_id`, `rtmr_extended`, `log_id`, `prev_log_id`, `mr_value`, `sequence_num`, `confirmed_at`
- [x] 1.2 Create `chain_state` table with `chain_id`, `head_record_id`, `head_log_id`, `sequence_num`, `mr_value`, `updated_at`
- [x] 1.3 Implement schema migration logic: detect legacy schema, ALTER TABLE to add missing columns, CREATE chain_state if absent
- [x] 1.4 Update `insert_record()` to accept and persist new fields
- [x] 1.5 Add `get_chain_state()` and `update_chain_state()` database functions
- [x] 1.6 Add `get_pending_by_chain()` to query pending records filtered by chain_id ordered by sequence_num

## 2. Trust API Sequencer Core

- [x] 2.1 Create Trust API FastAPI application skeleton (`trust_api.py`) with single-worker configuration
- [x] 2.2 Implement file-lock single-instance enforcement at `/dev/shm/tc_api_queue/trust-api.lock` using `fcntl.flock(LOCK_EX | LOCK_NB)`
- [x] 2.3 Implement `POST /commit` endpoint: acquire `threading.Lock()`, read chain_state, RTMR extend, INSERT commit_queue with `rtmr_extended=TRUE`, UPDATE chain_state, release lock
- [x] 2.4 Implement `GET /chain-state/{chain_id}` endpoint returning current chain state
- [x] 2.5 Implement `GET /status` endpoint returning queue statistics (queued_count, failed_count, next_sequence_num)
- [x] 2.6 Implement crash recovery on startup: retain `rtmr_extended=TRUE` + `PENDING` records, delete `rtmr_extended=FALSE` records, rebuild chain_state

## 3. Embedded Submit Daemon

- [x] 3.1 Implement submit daemon as `threading.Thread(daemon=True)` started in FastAPI lifespan
- [x] 3.2 Implement 5-second polling loop for `PENDING` records with `rtmr_extended=TRUE`
- [x] 3.3 Implement ordered Rekor submission: submit lowest `sequence_num` first, block on earlier PENDING/FAILED records
- [x] 3.4 Implement retry counting with max 10 retries, transition to `FAILED` on threshold
- [x] 3.5 Implement confirmed record update: set `status=CONFIRMED`, `confirmed_at`, `log_id`, update `chain_state.head_log_id`
- [x] 3.6 Implement FAILED record blocking: do not submit records with higher sequence_num when a FAILED record exists in the same chain

## 4. tc_api Refactoring

- [x] 4.1 Refactor tc_api commit handler: build DSSE predicate without `prev_log_id`, sign with sigstore offline mode
- [x] 4.2 Replace local `TrustedLogAPI.commit_record()` call with REST `POST` to Trust API `/commit` endpoint
- [x] 4.3 Add Trust API URL to `config.py` (environment-driven)
- [x] 4.4 Handle Trust API unavailability: return HTTP 503 to caller
- [x] 4.5 Remove process-local state (`_records`, `_entries`, `_latest_confirmed_log_id`) from tc_api commit path

## 5. DSSE Predicate Changes

- [x] 5.1 Remove `prev_log_id` from the DSSE predicate payload in tc_api signing code
- [x] 5.2 Ensure DSSE subject name follows `trusted-log-chain_{chain_id}` format

## 6. Verification Updates

- [x] 6.1 Implement Rekor search by DSSE subject name (`trusted-log-chain_{chain_id}`)
- [x] 6.2 Add signer identity filtering to discard entries not signed by the Trust API's workload identity
- [x] 6.3 Implement RTMR ordering proof: cross-check mr_value sequence against TDX attestation quote

## 7. Deployment Updates

- [x] 7.1 Update `docker-compose.yml`: replace `tlog-daemon` service with `trust-api` service, share `/dev/shm` tmpfs mount
- [x] 7.2 Update `start.sh`: remove `tlog_daemon.py` background launch, add Trust API startup with `--workers 1`
- [x] 7.3 Remove standalone `tlog_daemon.py` (replaced by embedded thread)

## 8. Testing

- [x] 8.1 Unit tests for expanded database schema and migration logic
- [x] 8.2 Unit tests for sequencer lock serialization (concurrent commit ordering)
- [x] 8.3 Unit tests for submit daemon ordering and retry/failure logic
- [x] 8.4 Integration test: tc_api signs → Trust API sequences → daemon submits to Rekor
- [x] 8.5 Crash recovery test: simulate crash at each stage, verify correct recovery behavior
- [x] 8.6 Single-instance enforcement test: verify second Trust API instance is rejected
