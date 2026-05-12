## Status

Superseded by `reservation-backed-replay-intents`.

These tasks are intentionally retained as historical context and should not be used as the execution checklist for implementation. Use the successor change's tasks instead, because the original task list does not account for the required reservation-backed `reserve -> sign -> commit(intent_token)` architecture.

## 1. Public Replay Payload Updates

- [ ] 1.1 Update tc_api DSSE predicate construction to emit signed `chain_id`, `sequence_num`, current `digest`, `prev_event_digest`, and `prev_lookup_hash` fields for replayable records.
- [ ] 1.2 Update Event Log 0 construction to emit `sequence_num = 1`, `prev_event_digest = null`, and `prev_lookup_hash = null` in the signed baseline payload.
- [ ] 1.3 Compute and persist `prev_lookup_hash` as predecessor DSSE `payloadHash(sha256)` for non-baseline records.

## 2. Immutable Replay Verification

- [ ] 2.1 Update immutable-backend replay in `TrustedLogAPI.verify_record()` to query Rekor candidates with `prev_lookup_hash`.
- [ ] 2.2 Add candidate filtering by `chain_id` and `sequence_num`, and confirm predecessor correctness by recomputing candidate `event_digest` against `prev_event_digest`.
- [ ] 2.3 Extend structured verification output to report predecessor verification failures and candidate-discovery results without relying on public `prev_log_id`.

## 3. TruCon Chain Verification

- [ ] 3.1 Replace non-TEE `prev_log_id` continuity checks in TruCon chain verification with signed predecessor continuity checks using `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`.
- [ ] 3.2 Update `/verify-chain/{chain_id}` response serialization to expose predecessor verification status and predecessor candidate counts.
- [ ] 3.3 Preserve pending-record behavior by reporting null predecessor verification fields when immutable-backend confirmation is not yet available.

## 4. Tests And Documentation

- [ ] 4.1 Update unit tests for Sigstore adapter and replay verification to cover multiple-candidate lookup, missing-candidate failures, and Event Log 0 null-predecessor behavior.
- [ ] 4.2 Extend opt-in public Rekor integration coverage to validate `payloadHash(sha256)` lookup and predecessor confirmation semantics.
- [ ] 4.3 Update architecture and verification docs to describe the new replay contract and the best-effort role of Rekor `/api/v1/index/retrieve`.