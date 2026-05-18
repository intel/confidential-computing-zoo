## 1. Schema & Database Setup

- [x] 1.1 Add SQLite dependency or setup standard python `sqlite3` integration (e.g., `database.py`).
- [x] 1.2 Create standard SQL schema representing local `CommitQueue` (fields: `record_id`, `event_id`, `payload`, `status`, `retry_count`, `updated_at`). 
- [x] 1.3 Refactor the legacy persistence logic in `tlog_chain.py`, migrating from `.sigstore.json` to the SQLite backend.

## 2. In-Toto DSSE & Sigstore SDK Integration

- [x] 2.1 Refactor SDK integration in `TrustedLogAPI` to construct In-Toto statements and operate in "offline mode" generating DSSE envelopes.
- [x] 2.2 Modify `commit_record()` to execute the OIDC to Fulcio certificate exchange synchronously.
- [x] 2.3 Modify `commit_record()` to save the fully-signed DSSE bundle to the SQLite queue and extend the local MR.

## 3. Submission Daemon Implementation

- [x] 3.1 Implement a Python `SubmissionDaemon` thread worker that periodically queries pending records in the SQLite database.
- [x] 3.2 Program the background worker to invoke the Sigstore Rekor transparency client natively to push static payloads, bypassing OIDC.
- [x] 3.3 Register daemon thread initialization and graceful shutdown events within the `main.py` FastAPI `lifespan` hook.

## 4. Verification and Testing

- [x] 4.1 Update `verify_record` to correctly parse and extract original `EventLog` metadata out of newly formatted DSSE envelopes.
- [x] 4.2 Write unit tests verifying DSSE formatting and tokenless Rekor pushes.
- [x] 4.3 Write SQLite integration and thread-safety tests confirming Write-Ahead-Log (WAL) prevents data drops.
