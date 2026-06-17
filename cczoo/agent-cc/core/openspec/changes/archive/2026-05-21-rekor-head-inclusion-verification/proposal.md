## Why

Current verification proves application-level replay continuity for the accepted Rekor-backed head, but it does not yet require proof that the accepted `head_log_id` was integrated into a signed Rekor tree state. That leaves a gap between the project's current verifier narrative and the stronger transparency-log guarantee operators expect when Rekor inclusion is treated as the public source of truth.

## What Changes

- Require verification of the accepted Rekor head entry's inclusion proof rather than treating entry readback alone as sufficient log verification.
- Require validation of the signed checkpoint or equivalent signed tree head associated with the accepted head entry's inclusion proof.
- Extend verifier result models and CLI output so replay continuity, head-entry log inclusion, checkpoint trust, and degraded proof availability are reported as separate dimensions.
- Define controlled first-trust bootstrap semantics for initial checkpoint trust without claiming full cross-time anti-fork guarantees.
- Preserve explicit degraded or troubleshooting-only outcomes when inclusion proof or checkpoint material is unavailable instead of collapsing those cases into success.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `tlog-chain-verification`: `TrustedLogAPI.verify_record()` must verify and report signed Rekor head-entry inclusion and checkpoint trust in addition to existing replay continuity findings.
- `chain-verification-cli`: `tc-verify` must surface head-entry inclusion, checkpoint validation, and degraded log-verification states separately from replay and attested-head results.

## Impact

- Affected code: Rekor adapter retrieval and proof handling, shared verification result normalization, and `tc-verify` rendering and JSON output.
- Affected systems: evidence-backed external verification, operator troubleshooting flows, and any automation consuming replay verification tiers.
- Dependencies: Rekor inclusion-proof and checkpoint retrieval/validation support, plus an explicit bootstrap trust source for the first verified checkpoint.