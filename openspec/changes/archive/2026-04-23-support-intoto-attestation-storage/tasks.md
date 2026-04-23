## 1. Rekor Entry Type Path

- [x] 1.1 Add an intoto v0.0.2 proposed-entry path in `SigstoreLogAdapter.submit_bundle()` while retaining the existing DSSE-type compatibility path.
- [x] 1.2 Add adapter configuration that selects the Rekor entry type without changing tc_api or TruCon's internal bundle persistence contract.
- [x] 1.3 Add unit tests that cover bundle-to-intoto conversion, embedded-log-entry reuse, and rollback compatibility with DSSE-type uploads.

## 2. Attestation-Storage Replay Materialization

- [x] 2.1 Extend Rekor entry normalization to preserve top-level `attestation` data and materialize replayable payload facts from it.
- [x] 2.2 Validate attestation payload content against the committed payload hash before using it for predecessor proof.
- [x] 2.3 Extend immutable replay provenance to distinguish `public`, `attestation-storage`, `mirror`, and cache-assisted fallback states.
- [x] 2.4 Add verifier unit tests for attestation-backed predecessor proof, invalid attestation rejection, and mirror fallback when attestation material is absent.

## 3. CLI and Policy Reporting

- [x] 3.1 Update CLI verification-tier logic to support `public+attestation-storage` in JSON and text output.
- [x] 3.2 Update diagnostics and human-readable summaries to explain Rekor attestation-storage materialization separately from OCI mirror usage.
- [x] 3.3 Add CLI tests covering attestation-storage-backed verification, mirror-required policy behavior, and mixed provenance summaries.

## 4. Real Rekor Integration Coverage

- [x] 4.1 Add a real-Rekor intoto round-trip smoke test that proves attestation-backed payload recovery.
- [x] 4.2 Add a real-Rekor multi-entry predecessor-proof smoke test that clears local cache and verifies without OCI mirror.
- [x] 4.3 Preserve DSSE-type real-Rekor regression coverage to document the existing public replay limit and fallback behavior.

## 5. Documentation and Rollout

- [x] 5.1 Update `docs/architecture.md` to describe intoto plus attestation storage as the primary replay-materialization design and OCI mirror as fallback.
- [x] 5.2 Update `docs/trusted-log/architecture.md` to document the revised trust boundary, provenance model, and migration strategy.
- [x] 5.3 Update testing guidance to describe the new intoto real-Rekor smoke path and the expected rollback strategy if public attestation-storage behavior changes.