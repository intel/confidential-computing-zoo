## 1. CLI input and mode plumbing

- [x] 1.1 Extend `tc-verify` argument parsing to accept an attested-head evidence input source while preserving the existing live `chain_id` fallback path.
- [x] 1.2 Add shared evidence loading and validation helpers that parse the v1 evidence package and recompute `report_data_binding.expected_value` from the bound fields.

## 2. Verification execution and result shaping

- [x] 2.1 Refactor verification execution so evidence-backed mode derives replay targets from the evidence package and checks replayed `chain_id`, `sequence_num`, `head_log_id`, and `mr_value` against the attested head.
- [x] 2.2 Reshape normalized JSON and human-readable output to report immutable replay, attested-head evidence, and live TruCon fallback as distinct result domains with clear mode labeling.
- [x] 2.3 Enforce evidence-specific failure handling for invalid packages, expired evidence, mismatched head association, and pending-only chains that are ineligible for evidence-backed verification.

## 3. Regression coverage and operator guidance

- [x] 3.1 Add CLI regression tests for evidence-backed success, invalid evidence, expired evidence, evidence-to-replay mismatch, and transitional live fallback behavior.
- [x] 3.2 Update verification documentation and test guidance to present evidence-backed verification as the preferred operator flow and live TruCon verification as fallback.