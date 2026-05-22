## Why

The current `sign -> /commit` flow cannot safely sign public predecessor fields such as `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`, because TruCon only knows the correct predecessor contract after it serializes access to chain state. We need a two-phase reservation model now because the earlier predecessor-replay proposal is blocked at apply time without a way to bind those fields into the signed DSSE payload.

## What Changes

- Add a reservation-backed commit-intent protocol in TruCon so callers can obtain a single-use, time-bounded predecessor contract before signing.
- **BREAKING** Change tc_api's trusted-log commit flow from one-shot `sign -> /commit` to `reserve -> sign -> commit(intent_token)` for replayable records.
- Bind idempotency to the whole intent lifecycle rather than only to the final `/commit` enqueue step.
- Extend Event Log 0 and lazy workload baseline creation so they use the same signed replay contract as later records.
- Update immutable replay and TruCon chain verification to treat Rekor lookup as candidate discovery and signed predecessor fields as protocol truth.
- Update architecture and API documentation under `docs/` to reflect the reservation protocol, the changed commit path, and the revised verification model.

## Capabilities

### New Capabilities
- `trucon-commit-intents`: reservation-backed predecessor-contract allocation, intent-token lifecycle, and commit-time intent consumption for replayable records.

### Modified Capabilities
- `tlog-rest-commit`: tc_api commit behavior changes from direct `/commit` posting to reservation-backed signing and intent-token submission.
- `tlog-sequencer`: sequencing responsibilities change so predecessor contract allocation happens during reservation and `/commit` validates rather than assigns ordering inputs.
- `trusted-log-sqlite-queue`: queue storage expands to persist intent lifecycle state and replay metadata needed by the new two-phase flow.
- `trucon-idempotency`: idempotency requirements move from commit-only deduplication to whole-intent reuse and conflict handling.
- `chain-initialization`: Event Log 0 and lazy workload baseline semantics change to use the same signed predecessor contract as later records.
- `tlog-chain-verification`: immutable replay verification changes to use signed predecessor proof plus Rekor candidate discovery instead of backend-assigned predecessor ids.
- `trucon-chain-verification`: TruCon verification output and continuity rules change to report signed predecessor verification rather than `prev_log_id` linkage.
- `chain-verification-cli`: operator-facing verification output changes to reflect reservation-backed replay continuity and the updated predecessor-verification fields.

## Impact

- Affected code includes `src/tc_api/tlog_client.py`, `src/tc_api/trucon/app.py`, `src/tc_api/trucon/database.py`, `src/tc_api/trucon/adapters/sigstore.py`, `src/tc_api/sigstore_baseline.py`, CLI verification paths, and regression tests.
- New internal API surface is required for reservation-backed commit intents, plus a changed `/commit` request contract that carries an intent token.
- The SQLite persistence model must add durable intent state for crash recovery, expiry, and idempotent retry handling.
- Architecture and API documentation must be updated in `docs/architecture.md`, `docs/trusted-log/architecture.md`, and `docs/trusted-log/api.md` so the shipped design matches the implemented control-plane flow.