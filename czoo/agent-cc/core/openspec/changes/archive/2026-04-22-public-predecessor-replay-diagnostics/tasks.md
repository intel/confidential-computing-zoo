## 1. Immutable Replay Diagnostics

- [x] 1.1 Extend immutable replay data structures to represent candidate discovery, candidate materialization, match counts, and `predecessor_status`
- [x] 1.2 Add immutable-backend candidate discovery support that does not rely on process-local cache as protocol truth
- [x] 1.3 Normalize discovered predecessor candidates before proof evaluation and restrict candidate-detail output to normalized replay facts
- [x] 1.4 Implement predecessor verdict classification for `origin`, `proven`, `missing`, `ambiguous`, `unverifiable`, `lookup_failed`, and `decode_failed`

## 2. TruCon Verification Output

- [x] 2.1 Update TruCon `/verify-chain/{chain_id}` result serialization to include `predecessor_status` and candidate-pipeline count fields for replayable records
- [x] 2.2 Add replay-boundary classification output for mixed legacy and reservation-backed proof regimes
- [x] 2.3 Keep TruCon predecessor vocabulary aligned with immutable replay semantics and remove any remaining dependence on `prev_log_id`-style truth in operator output

## 3. CLI Reporting

- [x] 3.1 Update CLI JSON normalization to preserve `predecessor_status`, candidate-pipeline counts, and replay-boundary classification
- [x] 3.2 Update human-readable CLI output to distinguish lookup failure, decode failure, missing match, ambiguity, degraded replay, and invalid replay
- [x] 3.3 Ensure CLI summary and fallback reporting remain consistent with the shared replay vocabulary

## 4. Validation

- [x] 4.1 Add or update tests for immutable replay candidate discovery, decode failure, no-match failure, ambiguity, and Event Log 0 origin handling
- [x] 4.2 Add or update tests for TruCon `/verify-chain` predecessor-status fields and replay-boundary classification
- [x] 4.3 Add or update CLI tests for JSON and human-readable predecessor diagnostics and degraded-versus-invalid rendering
- [x] 4.4 Run focused OpenSpec and test validation for the changed specs and verification surfaces