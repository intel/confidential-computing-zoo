## Why

The repository now has the core pieces of multi-chain public replay, Event Log 0 baseline validation, and attested-head evidence export, but the operator-facing verifier boundary is still split between the preferred evidence-backed path and a live TruCon fallback path. That split weakens the external verification story: operators can still treat internal control-plane APIs as a normal verifier input even though the architecture now says the long-term contract should be public replay plus exported evidence.

## What Changes

- Narrow the supported external verifier contract so operator-facing verification is defined by Rekor-backed replay plus exported attested-head evidence.
- Demote the current live `chain_id` verification path in `tc-verify` from a normal operator workflow to an explicitly internal or troubleshooting-only path.
- Update CLI behavior, result modeling, and documentation so fallback use is unmistakably non-primary and does not blur the external verifier boundary.
- Define the migration and compatibility posture for any remaining live TruCon verification entry points that continue to exist for local diagnostics.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `chain-verification-cli`: operator-facing verification inputs and result semantics change so evidence-backed verification becomes the only supported external verifier contract, while live `chain_id` fallback is demoted or isolated as an explicit troubleshooting path.

## Impact

- Affected code: `src/tc_api/cli/verify.py`, any helper code that fetches live TruCon verification data for fallback mode, and related docs/tests.
- Affected systems: operator workflows, JSON/text CLI output, and documentation describing external versus internal verification surfaces.
- Compatibility: users who currently rely on `tc-verify <chain_id>` as a normal operator path may need an explicit fallback flag, a separate troubleshooting mode, or a migration to exported evidence-based verification.