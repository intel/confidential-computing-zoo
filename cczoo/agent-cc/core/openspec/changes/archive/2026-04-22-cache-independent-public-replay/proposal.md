## Why

Public Rekor verification still relies on process-local bundle-derived replay helpers in some paths to recover DSSE payload facts that the verifier treats as trust-critical history. That weakens the external audit story because an auditor cannot cleanly distinguish facts that come directly from public Rekor materialization from facts that are reconstructed by project-local code.

## What Changes

- Define the verifier-facing provenance boundary for public replay so historical continuity facts must be recoverable from Rekor-auditable material rather than from process-local bundle cache truth.
- Preserve exported attested-head evidence as the current-head attestation surface only, and explicitly prevent it from becoming a carrier for replay-only historical baseline or predecessor facts.
- Tighten immutable replay requirements and operator reporting so the system distinguishes public-auditable replay facts from evidence-backed current-head binding.
- Expand cache-cleared and cross-process replay coverage so public predecessor proof and Event Log 0 baseline recovery are tested without relying on same-process submission state.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `tlog-chain-verification`: change immutable-backend replay requirements so verifier-critical historical facts are proven from Rekor-auditable materialization rather than process-local cache truth.
- `attested-head-evidence`: tighten the attested-head package boundary so evidence remains current-head binding only and does not replace Rekor-backed historical replay facts.
- `chain-verification-cli`: change operator-facing verification requirements so the CLI reports the provenance split between public replay facts and exported evidence binding.

## Impact

- Affected code: `src/tc_api/trucon/adapters/sigstore.py`, `src/tc_api/tlog_client.py`, `src/tc_api/cli/verify.py`, `src/tc_api/trucon/evidence.py`.
- Affected tests: public Rekor integration coverage, immutable replay regression tests, CLI verification output tests.
- Affected docs: trusted-log architecture, verification, and API documentation describing verifier trust boundaries.
- Affected systems: public Rekor replay, exported attested-head evidence, and operator verification workflows.