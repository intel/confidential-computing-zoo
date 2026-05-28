## Why

TruCon currently treats `chain_id` as if it can represent multiple independently replayable measured chains, but TDX only exposes one mutable physical RTMR[2]. That mismatch makes per-chain RTMR replay unsound and allows low-cost RTMR poisoning and cryptographic denial of service by interleaving non-default chain traffic into the shared register.

## What Changes

- **BREAKING** Collapse RTMR-backed sequencing, verification, and evidence export to one admitted measured chain: `default`.
- **BREAKING** Reject non-default chain initialization, commit reservation, and commit admission, and remove parameterized measured read APIs in favor of default-only endpoints (`/chain-state`, `/verify-chain`, `/evidence`, `/confidential/evidence`, `/confidential/posture`).
- Preserve `workload_id`, `instance_id`, container labels, and related metadata as bookkeeping and query dimensions rather than as physical measurement-chain boundaries.
- Update tc_api, Docktap, verification tooling, and operator documentation to stop deriving measured-chain identity from workload identity.
- Require a fresh default-chain epoch during rollout so already-poisoned multi-chain RTMR state is not silently carried forward as if it were trustworthy.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `workload-chain-routing`: workload labels remain metadata, but they no longer select an independent measured chain.
- `docktap-trucon-commit`: Docktap runtime events always commit to the default measured chain and share one global sequence.
- `chain-initialization`: only the default chain may bootstrap Event Log 0; non-default chain bootstrap is rejected.
- `trucon-chain-verification`: cryptographic verification is only defined for the default measured chain.
- `attested-head-evidence`: exported quote-backed head evidence is only defined for the default measured chain.

## Impact

- Affected code: TruCon admission and query endpoints, tc_api trusted-log client, Docktap TruCon client, attested-head export, verification surfaces, and related tests.
- Affected APIs: `/commit-intents/reserve`, `/init-chain/{chain_id}/baseline`, `/init-chain`, `/commit`, `/chain-state`, `/verify-chain`, `/evidence`, `/confidential/evidence`, and `/confidential/posture`.
- Operational impact: deployments with existing multi-chain history need an operator-managed fresh default-chain epoch instead of in-place trust continuity.
- Documentation impact: architecture, API, testing, and verification docs must stop describing per-workload chains as independent RTMR-backed trust chains.