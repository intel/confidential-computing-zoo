## 1. Baseline Owner Bootstrap

- [x] 1.1 Define the baseline owner-attestation data model, serialization, and persistence contract for Event Log 0.
- [x] 1.2 Update chain initialization flows so Event Log 0 declares a single long-term owner public key and persists owner-attestation material.
- [x] 1.3 Add tests covering successful baseline owner bootstrap, missing attestation rejection, and non-default chain initialization semantics.

## 2. Commit Admission

- [x] 2.1 Extend reservation-backed commit request handling to carry and validate owner-key authorization in addition to predecessor-contract matching.
- [x] 2.2 Persist owner-authorization material needed for later replay verification of confirmed records.
- [x] 2.3 Add tests covering successful owner-authorized commits, missing owner authorization rejection, and idempotent/replayed intent behavior.

## 3. Verification And Operator Surfaces

- [x] 3.1 Extend verification models and logic to report `owner_ok` and `owner_status` independently from predecessor continuity.
- [x] 3.2 Update verifier-facing CLI or diagnostics so owner-authorization failures are visible and distinguishable from predecessor failures.
- [x] 3.3 Add tests covering confirmed owner-proof success, owner-proof failure, and pending owner-unverifiable states.

## 4. Documentation And Rollout

- [x] 4.1 Document the single-owner trust model, including the distinction between baseline owner attestation and current-head attested evidence.
- [x] 4.2 Document rollout constraints and backward-compatibility expectations for producers that currently submit only predecessor-backed replayable commits.