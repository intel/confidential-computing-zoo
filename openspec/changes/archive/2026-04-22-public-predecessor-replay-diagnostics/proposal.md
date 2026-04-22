## Why

The reservation-backed replay contract is in place, but public immutable-backend verification still depends on process-local cache behavior and under-specified predecessor diagnostics. We need a follow-on change now so public replay can discover predecessor candidates from Rekor, classify predecessor-proof outcomes precisely, and present consistent operator-facing results across TruCon and the CLI.

## What Changes

- Add spec-level requirements for immutable-backend predecessor candidate discovery that do not rely on process-local replay caches as protocol truth.
- Define stable predecessor diagnostic fields and pipeline counts for replay results, including classification of lookup failure, decode failure, missing matches, and ambiguity.
- Update TruCon `/verify-chain/{chain_id}` requirements to expose predecessor verification as a classified machine-readable outcome rather than only a boolean.
- Update chain verification CLI requirements so JSON and human-readable output preserve the same predecessor vocabulary and clearly distinguish degraded replay from invalid replay.
- Define operator-facing handling for replay regime boundaries, including legacy-to-reservation transitions and reservation-to-legacy regressions.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `tlog-chain-verification`: immutable-backend replay requirements expand to cover public predecessor candidate discovery, normalization, and structured predecessor diagnostics.
- `trucon-chain-verification`: `/verify-chain` response requirements expand to include classified predecessor status and candidate-pipeline visibility for replayable records.
- `chain-verification-cli`: operator-facing verification output requirements expand to preserve predecessor diagnostics and explicit replay-boundary classifications.

## Impact

- Affected code is expected to include immutable replay and Rekor adapter logic in `src/tc_api/tlog_client.py`, `src/tc_api/tlog/immutable.py`, and `src/tc_api/trucon/adapters/sigstore.py`.
- TruCon verification output in `src/tc_api/trucon/app.py` and CLI rendering in `src/tc_api/cli/verify.py` will need to converge on the same predecessor result vocabulary.
- Tests covering immutable replay, TruCon verification, and CLI reporting will need to expand around candidate discovery, ambiguity handling, and mixed-format boundary behavior.
- Documentation and operator guidance may need follow-up updates once the new replay-diagnostics contract is implemented.