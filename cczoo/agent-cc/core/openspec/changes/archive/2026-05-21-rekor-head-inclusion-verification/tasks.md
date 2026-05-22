## 1. Rekor Proof Retrieval

- [x] 1.1 Extend the Rekor adapter to retrieve normalized inclusion-proof material for the accepted `head_log_id`.
- [x] 1.2 Add checkpoint or signed-tree-head retrieval and signature validation support behind an explicit bootstrap trust source.
- [x] 1.3 Normalize proof-fetch outcomes so unavailable proof material, invalid proof material, and invalid checkpoint trust are distinguishable.

## 2. Shared Verification Integration

- [x] 2.1 Extend `TrustedLogAPI.verify_record()` result structures to carry accepted head-entry inclusion status, checkpoint validation status, and degraded reasons.
- [x] 2.2 Integrate accepted head-entry inclusion verification into the immutable-backend verification flow without changing existing replay continuity semantics.
- [x] 2.3 Ensure bootstrap-trusted head verification does not claim historical consistency across time.

## 3. CLI Reporting

- [x] 3.1 Update `tc-verify` JSON output to report head-entry inclusion and checkpoint validation separately from replay and attested-head results.
- [x] 3.2 Update human-readable CLI summaries to distinguish verified, degraded, failed, and troubleshooting-only log-verification outcomes.
- [x] 3.3 Surface bootstrap-trust limitations clearly in CLI output when accepted head verification succeeds without historical consistency proof.

## 4. Verification Coverage

- [x] 4.1 Add or update tests for successful accepted head-entry inclusion verification with valid checkpoint trust.
- [x] 4.2 Add or update tests for degraded outcomes when proof or checkpoint material is unavailable.
- [x] 4.3 Add or update tests for hard failures when inclusion proof or checkpoint validation is cryptographically invalid.