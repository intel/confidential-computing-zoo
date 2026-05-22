## Why

Remote verification now has a documented direction, but the repository still lacks a frozen v1 contract for exported attested head evidence. Without that contract, TruCon cannot expose a stable evidence package and `tc-verify` cannot reliably evolve away from live in-CVM API dependencies.

## What Changes

- Define a v1 attested head evidence contract for remote verification, including the minimum required fields, freshness metadata, and explicit association to a public Rekor chain head.
- Specify how quote-backed evidence binds the current chain head to current CVM state, including which fields are mandatory in the exported package and which are optional extensions.
- Document the canonical serialization shape and validation rules so TruCon, `tc-verify`, and test fixtures can share one evidence model.
- Clarify the trust boundary between Event Log 0 as the epoch baseline anchor and attested head evidence as the current-state checkpoint.

## Capabilities

### New Capabilities
- `attested-head-evidence`: A stable v1 contract for exported attested head evidence that binds a public chain head to current attested CVM state.

### Modified Capabilities
- None.

## Impact

- Affected code: future TruCon evidence export paths, `tc-verify` evidence input handling, shared verification model types, and test fixtures.
- Affected systems: remote operator verification workflows and the boundary between in-CVM control APIs and external verification surfaces.
- Affected docs: `docs/trusted-log/verification.md`, `docs/trusted-log/architecture.md`, and follow-on OpenSpec artifacts for evidence export and evidence-backed verification.