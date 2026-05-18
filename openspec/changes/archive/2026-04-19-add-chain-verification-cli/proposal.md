## Why

Operators and auditors currently have to stitch together verification from library calls, TruCon HTTP endpoints, and ad hoc inspection of immutable backend state. That leaves the verification plane implemented but not productized: there is no stable package-level CLI that performs a full chain check, emits a consistent machine-readable result, and makes non-TEE fallback behavior explicit.

## What Changes

- Add a package-integrated verification CLI for trust chains, exposed as a dedicated console command and scoped to `chain_id` input.
- Make the CLI aggregate two verification sources: immutable-backend replay verification as the primary verdict source, and TruCon local chain verification as the secondary source for ordering and measurement diagnostics.
- Define a stable CLI-owned JSON result model that includes summary status, verification mode, source-level outcomes, and per-record detail.
- Add operator-facing flags for signer identity filtering, expected entry count, pending-record failure policy, and mandatory TEE enforcement.
- Classify non-TEE verification as test-only fallback behavior rather than production-equivalent success.

## Capabilities

### New Capabilities
- `chain-verification-cli`: A package-level CLI for chain verification with human-readable and JSON output, using `chain_id` as the only primary selector.

### Modified Capabilities
- `tlog-chain-verification`: Immutable-backend replay verification needs richer structured output and policy inputs so the CLI can present stable per-record results and enforce caller-specified verification constraints.

## Impact

- Affected code: package CLI entry points, new `src/tc_api/cli/` module(s), `src/tc_api/tlog_client.py`, and CLI-oriented tests.
- Affected systems: operator and auditor workflows, immutable-backend verification path, TruCon-assisted verification diagnostics.
- Affected docs: `README.md`, `docs/TESTING.md`, and trusted-log documentation describing verification usage and result semantics.