## 1. Public Rekor Proof Coverage

- [x] 1.1 Add focused real-Rekor integration coverage for a multi-entry replayable chain that proves signed predecessor continuity across more than one public entry
- [x] 1.2 Ensure the public-Rekor proof test validates candidate discovery and normalized predecessor matching rather than process-local predecessor cache adjacency alone
- [x] 1.3 Add focused regression coverage for public predecessor outcomes such as missing match and ambiguous match when Rekor returns multiple candidates

## 2. Rollout Boundary Classification

- [x] 2.1 Implement stable replay-boundary classification for legacy-to-reservation migration boundaries in immutable replay results
- [x] 2.2 Implement stronger invalid classification for reservation-to-legacy regressions after a chain has entered the reservation-backed regime
- [x] 2.3 Propagate the shared boundary classification through TruCon `/verify-chain/{chain_id}` output independently from RTMR availability

## 3. CLI And Operator Guidance

- [x] 3.1 Preserve replay-boundary classification in CLI JSON output without reducing it to free-form summary text
- [x] 3.2 Update human-readable CLI summaries to distinguish supported reservation-backed replay, degraded mixed-regime migration state, and invalid regression
- [x] 3.3 Update trusted-log verification and testing docs to explain the public-Rekor rollout contract and the meaning of the new mixed-regime outcomes

## 4. Validation

- [x] 4.1 Run focused verification tests covering immutable replay, TruCon verification, and CLI reporting for mixed-regime and public-Rekor predecessor-proof cases
- [x] 4.2 Validate the OpenSpec change so `public-rekor-rollout-hardening` is apply-ready with proposal, design, specs, and tasks accepted