## Why

The current DSSE-to-Rekor path often leaves public replay with hash-only entry bodies, which forces tc_api to depend on process-local cache or the OCI bundle mirror to reconstruct verifier-critical predecessor fields. Because this project is still in prototype stage and the public Rekor instance appears to support attestation storage for `intoto` uploads, this is the right time to shift the primary replay-materialization path toward `intoto` plus attestation storage while keeping OCI mirror as a compatible fallback.

## What Changes

- Add a primary Rekor upload path that submits replayable records as `intoto` v0.0.2 entries while preserving the existing internal DSSE bundle contract between tc_api, TruCon, and the embedded submitter.
- Extend immutable replay so verification can materialize predecessor payload facts from Rekor attestation storage before falling back to cache or OCI mirror.
- Update verification provenance, policy handling, and CLI output to distinguish `public+attestation-storage` from `public-only` and `public+mirrored` results.
- Retain OCI bundle mirror support as a fallback and operator-controlled policy path rather than the default materialization mechanism.
- Add real Rekor integration coverage for `intoto` upload and verify flows, and update architecture and trusted-log design documentation to describe the migration target and fallback boundaries.

## Capabilities

### New Capabilities
- `rekor-intoto-attestation-storage`: Use Rekor `intoto` v0.0.2 entries and attestation storage as the primary public replay-materialization path for replayable tc_api records.

### Modified Capabilities
- `oci-bundle-mirror`: Change OCI mirror from the default replay-materialization path to a fallback and policy-driven compatibility path.
- `tlog-chain-verification`: Extend immutable replay to materialize predecessor payloads from Rekor attestation storage and report `attestation-storage` provenance.
- `chain-verification-cli`: Extend CLI summaries, diagnostics, and verification tiers to distinguish attestation-storage-backed replay from mirrored replay.

## Impact

- Affected code: `src/tc_api/trucon/adapters/sigstore.py`, `src/tc_api/tlog_client.py`, `src/tc_api/cli/verify.py`, and related real-Rekor integration paths.
- Affected tests: `tests/test_tlog_impl.py`, `tests/test_verify_cli.py`, `tests/test_real_rekor_integration.py`, plus mirror fallback regression coverage.
- Affected systems: public Rekor upload and retrieval semantics, immutable replay provenance, mirror policy enforcement, and operator verification output.
- Affected docs: `docs/architecture.md`, `docs/trusted-log/architecture.md`, and testing guidance for real Rekor verification.