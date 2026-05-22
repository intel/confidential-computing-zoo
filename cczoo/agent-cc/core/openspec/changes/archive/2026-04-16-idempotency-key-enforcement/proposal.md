## Why

A network timeout or retry between tc_api and TruCon causes the same event to be committed twice — each commit extends the RTMR, permanently corrupting the hardware measurement chain with no recovery path. This is a live data-integrity risk in a normal failure mode (TCP timeout + automatic retry). Idempotency key enforcement prevents duplicate RTMR extends by detecting retried commits and returning the original response.

## What Changes

- TruCon `POST /commit` accepts an optional `idempotency_key` field for duplicate detection.
- Within the sequencer lock, TruCon checks for an existing record with the same `idempotency_key` and `chain_id` before performing RTMR extend or SQLite insert.
- Duplicate commits return the original `CommitResponse` without re-extending RTMR.
- tc_api's `TrustedLogAPI.commit_record()` generates a random idempotency key per commit attempt and includes it in every `POST /commit` request.
- The `commit_queue` SQLite table gains an `idempotency_key` column with a UNIQUE constraint.
- Legacy schema migration adds the new column to existing databases.
- When a duplicate matches a FAILED record, the FAILED status is returned as-is — the caller must use a new key to retry with fresh intent, consistent with the architecture's "FAILED records need operator intervention" principle.

## Capabilities

### New Capabilities
- `trucon-idempotency`: Idempotency key enforcement for the TruCon commit path — covers key generation, duplicate detection inside the sequencer lock, schema changes, and migration.

### Modified Capabilities
- `tlog-rest-commit`: The REST commit path gains an `idempotency_key` parameter in the payload sent from tc_api to TruCon.

## Impact

- **Code**: `src/tc_api/trucon/app.py` (CommitRequest model, /commit handler), `src/tc_api/trucon/database.py` (schema, migration, insert, new query), `src/tc_api/tlog_client.py` (key generation, payload).
- **API**: `POST /commit` request body gains an optional `idempotency_key` field. Fully backward compatible — omitting the key disables deduplication.
- **Storage**: `commit_queue` table gains one TEXT column with a UNIQUE constraint. Existing rows will have NULL idempotency_key (no constraint violation).
- **Tests**: New unit tests for dedup logic, concurrent identical requests, migration, and client-side key generation.
