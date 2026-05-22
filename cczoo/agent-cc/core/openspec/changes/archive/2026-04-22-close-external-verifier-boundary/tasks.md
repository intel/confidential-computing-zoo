## 1. CLI Contract Tightening

- [x] 1.1 Update `tc-verify` argument parsing so evidence-backed verification is the supported default operator path and bare `chain_id` invocation no longer implies normal external verification.
- [x] 1.2 Add an explicit troubleshooting selector for live TruCon-backed verification and label that mode as internal or troubleshooting-only in help text and runtime mode metadata.
- [x] 1.3 Adjust normalized JSON and human-readable output so troubleshooting-mode results cannot be mistaken for supported external verifier results.

## 2. Documentation And Compatibility Guidance

- [x] 2.1 Update trusted-log verification, API, README, and top-level architecture docs to describe evidence-backed verification as the external contract and live TruCon verification as an internal troubleshooting path only.
- [x] 2.2 Add operator-facing migration guidance for users who currently rely on `tc-verify <chain_id>` so the new entry contract and troubleshooting path are explicit.

## 3. Validation

- [x] 3.1 Add or update CLI tests for rejected bare-`chain_id` external verification, explicit troubleshooting-mode invocation, and mode labeling in JSON and text output.
- [x] 3.2 Run focused CLI and verification tests plus `openspec validate --specs --strict` to confirm the tightened verifier boundary and updated specs remain consistent.