## 1. Reservation Core

- [x] 1.1 Add durable `commit_intents` storage, replay-metadata columns, and startup recovery/expiry handling in the TruCon SQLite layer.
- [x] 1.2 Implement the TruCon reservation endpoint that allocates `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` under the sequencer lock and enforces the single-active-intent-per-chain rule.
- [x] 1.3 Update TruCon `/commit` to accept `intent_token`, validate the signed bundle against the reserved contract, consume the intent, and persist the reserved replay metadata on success.
- [x] 1.4 Rework TruCon lifecycle idempotency so retries with the same `chain_id` and `idempotency_key` return the existing intent or the original commit result instead of creating duplicates.

## 2. tc_api And Baseline Flow

- [x] 2.1 Update `TrustedLogAPI.commit_record()` and related tc_api commit paths to perform `reserve -> sign -> commit(intent_token)` with one shared idempotency key.
- [x] 2.2 Extend DSSE predicate construction and baseline signing so replayable records include signed `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` fields.
- [x] 2.3 Rework Event Log 0 and workload bootstrap to use baseline snapshot plus reserved baseline intent, and update `POST /init-chain` handling accordingly.

## 3. Verification And Replay

- [x] 3.1 Update immutable replay and Rekor traversal logic to verify signed predecessor continuity using `prev_event_digest`, `sequence_num`, and `prev_lookup_hash` as candidate-discovery input only.
- [x] 3.2 Replace TruCon non-TEE `prev_log_id` continuity checks with signed predecessor verification and update `/verify-chain/{chain_id}` response fields to expose `predecessor_ok` and related diagnostics.
- [x] 3.3 Update the verification CLI JSON and human-readable outputs to report signed predecessor continuity findings instead of backend-specific predecessor-id linkage.

## 4. Tests And Documentation

- [x] 4.1 Add unit and integration coverage for reservation races, intent expiry, retry reuse, baseline bootstrap, and commit-time bundle-vs-intent mismatch handling.
- [ ] 4.2 Extend replay and public Rekor tests to cover Event Log 0 null-predecessor semantics, multiple-candidate lookup, and signed predecessor proof failures.
- [x] 4.3 Update `docs/architecture.md`, `docs/trusted-log/architecture.md`, and `docs/trusted-log/api.md` so the published architecture and API flow match the reservation-backed design.