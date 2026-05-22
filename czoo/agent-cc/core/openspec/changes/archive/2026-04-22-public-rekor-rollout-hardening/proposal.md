## Why

The signed predecessor replay contract is already in place, but public Rekor verification still has rollout debt around mixed-regime chains and limited end-to-end confirmation against real multi-entry Rekor history. We need a narrow hardening change now so operators have deterministic rollout rules and the public-Rekor path is covered by tests that exercise the predecessor-proof contract under realistic conditions.

## What Changes

- Define rollout requirements for public Rekor verification when chains cross replay-proof regime boundaries, including how verifiers classify legacy-only segments, reservation-backed segments, and unsupported regressions.
- Require real-Rekor integration coverage for multi-entry predecessor proof so public replay validates the signed `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` contract against fetched Rekor candidates rather than only against local or synthetic fixtures.
- Tighten operator-facing verification behavior so mixed-regime results surface deterministic machine-readable boundary classifications and clear rollout guidance.
- Add implementation hardening around public Rekor candidate discovery and regression tests for ambiguous, missing, and mixed-regime predecessor outcomes that can arise during rollout.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `tlog-chain-verification`: replay requirements expand to cover public-Rekor rollout boundaries and real-Rekor multi-entry predecessor-proof confirmation.
- `trucon-chain-verification`: local verification requirements expand to classify mixed legacy/reservation replay boundaries with stable operator-facing status.
- `chain-verification-cli`: CLI requirements expand to preserve rollout-boundary diagnostics and present clear mixed-regime guidance in JSON and human-readable output.

## Impact

- Affected code is expected to include public immutable replay and Rekor adapter paths in `src/tc_api/tlog_client.py` and `src/tc_api/trucon/adapters/sigstore.py`, plus TruCon verification output in `src/tc_api/trucon/app.py` and CLI rendering in `src/tc_api/cli/verify.py`.
- Test impact is concentrated in immutable replay, public Rekor integration, TruCon verification, and CLI reporting suites, especially coverage for multi-entry predecessor proofs and mixed-regime boundaries.
- Operator and rollout documentation will need updates in the trusted-log verification and testing docs so the rollout contract for public Rekor is explicit and testable.