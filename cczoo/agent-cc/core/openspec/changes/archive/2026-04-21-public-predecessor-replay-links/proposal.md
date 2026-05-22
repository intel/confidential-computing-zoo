## Status

Superseded by `reservation-backed-replay-intents`.

This change is kept for historical context only and should not be applied as the active implementation plan. During apply analysis, it became clear that the one-shot `sign -> /commit` architecture cannot safely sign `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`, because TruCon does not know the authoritative predecessor contract until it serializes chain access. The replacement change adopts the required two-phase reservation-backed design.

## Why

Public replay currently depends on `prev_log_id`, which is a backend-assigned Rekor identifier rather than a protocol-level predecessor proof. That makes replay brittle for asynchronous sequencing, ties the chain contract to one immutable backend's addressing model, and limits future evolution toward backend-independent verification.

## What Changes

- Replace public predecessor linkage based on `prev_log_id` with a signed replay contract built from `prev_event_digest`, `sequence_num`, and `prev_lookup_hash`.
- Define `prev_lookup_hash` as the predecessor DSSE `payloadHash(sha256)` so Rekor can be used for best-effort candidate discovery through `/api/v1/index/retrieve`.
- Update immutable-backend verification so candidate discovery and predecessor proof are treated as separate concerns: Rekor lookup finds candidates, while signed chain fields prove correctness.
- Update TruCon chain verification to stop treating `prev_log_id` as the public non-TEE predecessor proof and instead validate predecessor continuity using the new replay fields.
- Update Event Log 0 semantics so baseline records explicitly represent a null predecessor (`sequence_num=1`, `prev_event_digest=null`, `prev_lookup_hash=null`).
- Document that Rekor index lookup may return multiple or incomplete candidates and that correctness is enforced by signed replay fields rather than index uniqueness.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `tlog-chain-verification`: immutable-backend replay verification will use signed predecessor fields and Rekor-searchable lookup hashes instead of public `prev_log_id` linkage.
- `trucon-chain-verification`: chain verification will validate predecessor continuity using `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` rather than non-TEE `prev_log_id` checks.
- `chain-initialization`: Event Log 0 requirements will be updated to define the null-predecessor form of the public replay contract for baseline records.

## Impact

- Affected code includes `src/tc_api/tlog_client.py`, `src/tc_api/trucon/app.py`, `src/tc_api/trucon/adapters/sigstore.py`, attested verification flows, and public Rekor integration tests.
- Public DSSE predicate contents and replay semantics will change, which affects verifier behavior and documentation for operators using Rekor-backed replay.
- The change continues to rely on Rekor `/api/v1/index/retrieve` for candidate discovery, but only as a best-effort search surface rather than a source of protocol truth.