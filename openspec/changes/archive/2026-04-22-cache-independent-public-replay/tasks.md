## 1. Replay Provenance Boundary

- [x] 1.1 Audit the Sigstore adapter and immutable replay path to identify every verifier-critical fact that currently depends on process-local bundle cache rather than Rekor-auditable materialization.
- [x] 1.2 Refactor `src/tc_api/trucon/adapters/sigstore.py` and `src/tc_api/tlog_client.py` so cache-derived data is used only as a fetch optimization and cannot upgrade historical replay to publicly verified proof.
- [x] 1.3 Update immutable replay result classification so missing public materialization for Event Log 0 or predecessor proof is reported as degraded, unsupported, or failed instead of silently passing via local reconstruction.

## 2. Evidence And Operator Boundary

- [x] 2.1 Tighten the attested-head evidence contract and validators so exported evidence remains current-head binding only and replay-only historical facts do not satisfy public replay obligations.
- [x] 2.2 Update `src/tc_api/cli/verify.py` to report the provenance split between public replay facts and evidence-backed current-head binding in both JSON and human-readable output.
- [x] 2.3 Ensure CLI summary logic does not present cache-assisted historical reconstruction as fully verified public history when evidence succeeds but public replay provenance does not.

## 3. Coverage And Documentation

- [x] 3.1 Add unit and integration coverage for cache-cleared or fresh-process replay, including Event Log 0 baseline recovery and multi-entry predecessor proof without shared in-process cache state.
- [x] 3.2 Add evidence and CLI regression tests that preserve the boundary between public replay proof and exported attested-head evidence.
- [x] 3.3 Update trusted-log architecture, verification, API, and testing documentation to describe the new public audit boundary and any new operator-facing provenance states.
- [x] 3.4 Run focused verification tests and `openspec validate --specs --strict`, then resolve any spec or test regressions before implementation is considered complete.