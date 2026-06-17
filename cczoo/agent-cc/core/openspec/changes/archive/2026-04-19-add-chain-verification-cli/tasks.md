## 1. Immutable Verification Enrichment

- [x] 1.1 Extend immutable-backend verification output in `TrustedLogAPI.verify_record()` to return structured per-entry details and policy-related metadata needed by the CLI
- [x] 1.2 Add or update tests covering signer-identity filtering, expected-entry-count reporting, and structured immutable-backend failure cases

## 2. Package CLI Surface

- [x] 2.1 Add a package CLI entry point for chain verification and wire it through package metadata
- [x] 2.2 Implement CLI argument parsing for `chain_id`, `--signer-identity`, `--expected-entry-count`, `--fail-on-pending`, `--require-tee`, and `--json`
- [x] 2.3 Implement normalized result assembly that combines immutable-backend replay results with TruCon `/verify-chain/{chain_id}` diagnostics

## 3. Output Semantics and Policy Handling

- [x] 3.1 Implement the stable CLI JSON result model and default human-readable rendering with per-record detail
- [x] 3.2 Implement overall verdict logic for pending entries, source failures, and `--require-tee` / non-TEE fallback classification
- [x] 3.3 Add tests covering TEE success, non-TEE test-only fallback, pending handling, and mixed-source diagnostic output

## 4. Documentation and Verification

- [x] 4.1 Document the CLI usage and output semantics in `README.md` and `docs/TESTING.md`
- [x] 4.2 Update trusted-log documentation to reference the package CLI as the operator-facing verification entry point
- [x] 4.3 Run targeted tests for immutable-backend verification, TruCon chain verification, and the new CLI surface