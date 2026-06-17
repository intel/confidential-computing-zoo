## Why

Public Rekor verification can prove that a DSSE entry was included in the transparency log, but it cannot reliably materialize the full signed payload needed for complete predecessor replay after local cache is cleared. That leaves a gap between public inclusion proof and historical replay completeness, so newly written chain nodes need a non-authoritative materialization layer that can restore the original bundle without changing Rekor's role as the source of public proof.

## What Changes

- Introduce an OCI-backed bundle mirror capability that stores the original `bundle.json` for newly written replayable chain nodes after Rekor confirmation.
- Define `payload_hash` as the primary mirror lookup anchor and treat human-readable fields such as `chain_id`, `sequence_num`, and `event_digest` as secondary indexes only.
- Extend immutable-backend replay verification so it can materialize predecessor inputs from the mirror when public Rekor entry data cannot recover a replayable payload on its own.
- Extend operator-facing verification results so they distinguish `public-only`, `public+mirrored`, and `public+mirrored+attested` outcomes rather than collapsing them into one undifferentiated success state.
- Require a feasibility spike or test harness that proves OCI publication, lookup by `payload_hash`, intact retrieval, and well-defined verifier behavior when mirror content is missing or delayed.

## Capabilities

### New Capabilities
- `oci-bundle-mirror`: Mirror original replayable bundles into OCI artifact storage using content-addressed lookup anchored by `payload_hash`.

### Modified Capabilities
- `tlog-chain-verification`: Immutable replay verification adds mirror-backed materialization and structured provenance for public-only versus mirrored replay.
- `chain-verification-cli`: CLI output and policy handling distinguish public-only, mirrored, and attested verification tiers.

## Impact

- Affected code: immutable-log adapters, `TrustedLogAPI.verify_record()`, verification policy/profile handling, TruCon post-confirmation publish flow, and CLI result rendering.
- Affected systems: public Rekor integration, OCI registry integration, and operator-facing verification workflows.
- New dependencies: OCI artifact publication and retrieval plumbing for mirrored `bundle.json` objects.
- Operational impact: mirror publication becomes an asynchronous post-confirmation step and verifier policy determines whether mirror availability is optional or required.