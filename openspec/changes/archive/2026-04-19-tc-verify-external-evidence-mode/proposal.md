## Why

`tc-verify` is still centered on live TruCon control-plane endpoints even though the architecture now treats exported attested-head evidence plus Rekor replay as the long-term remote-verifier contract. This leaves the verification plane in a transitional state where operators still need live service reachability for the main CLI path, which weakens the intended trust boundary and blocks the next layer of profile-based verification work.

## What Changes

- Make evidence-backed verification the primary `tc-verify` mode by allowing the CLI to consume an attested-head evidence package and derive replay targets from that package.
- Verify that immutable-backend replay reaches the attested chain head described by exported evidence, and report replay findings separately from attested-head findings.
- Keep live TruCon-backed verification as an explicitly marked fallback path rather than the default verification contract.
- Tighten CLI UX, JSON output, and failure modes around missing evidence, mismatched evidence-to-chain association, stale or pending-only heads, and TEE-required policies.
- Update operator-facing documentation to reflect evidence-backed verification as the preferred path.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `chain-verification-cli`: change the CLI contract so evidence-backed verification is the primary mode, with live TruCon verification retained only as a transitional fallback and with distinct replay-versus-attestation reporting.

## Impact

- Affected code: `src/tc_api/cli/verify.py`, shared verification helpers in `src/tc_api/tlog_client.py` and `src/tc_api/trucon/evidence.py` if needed for evidence parsing and validation.
- Affected tests: `tests/test_verify_cli.py` plus targeted verification-plane regressions for evidence input, fallback mode, and mismatch handling.
- Affected docs: `docs/trusted-log/verification.md`, `docs/TESTING.md`, and any CLI usage references in `README.md`.
- External behavior: `tc-verify` gains evidence-package inputs and changes its default trust boundary from live TruCon state toward exported evidence plus public replay.