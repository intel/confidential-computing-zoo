## Why

The current Event Log 0 `pub_key` is recorded in the baseline payload but does not define a durable ownership model for later writes. This leaves the chain with continuity proof but without an intrinsic, chain-local notion of a single long-term writer identity anchored at initialization time.

## What Changes

- Redefine the Event Log 0 `pub_key` as a single long-term chain owner public key rather than an ephemeral baseline artifact.
- Add a baseline attestation contract that binds the declared owner public key to TEE-backed initialization context.
- Require reservation-backed replayable commits to carry owner-key authorization in addition to signed predecessor continuity.
- Extend chain verification to report whether historical writes remain authorized by the chain owner key declared at Event Log 0.
- Clarify that current-head attested evidence remains separate from baseline owner attestation.

## Capabilities

### New Capabilities
- `chain-root-owner-attestation`: Defines the baseline attestation contract that binds a single-owner chain root public key to Event Log 0 initialization context and TEE-backed evidence.

### Modified Capabilities
- `chain-initialization`: Event Log 0 initialization now establishes a long-lived owner key and persists owner-attestation material needed to bootstrap chain authority.
- `trucon-commit-intents`: Reservation-backed commits now require chain-owner authorization in addition to predecessor-contract matching.
- `trucon-chain-verification`: Verification now checks owner-key continuity for confirmed replayable records and reports owner-authorization status distinctly from predecessor continuity.

## Impact

- Affects TruCon initialization, commit admission, and verification flows in `src/tc_api/trucon/app.py` and related models/adapters.
- Introduces a new baseline attestation artifact and verifier contract distinct from attested-head evidence.
- Requires changes to baseline bundle construction, commit request semantics, queue payload persistence, and verification tooling.
- Preserves existing internal service authentication but adds a chain-local authorization layer for replayable writes.