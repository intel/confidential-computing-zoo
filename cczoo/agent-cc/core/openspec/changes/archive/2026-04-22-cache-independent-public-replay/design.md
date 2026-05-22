## Context

The current public-Rekor verification path already distinguishes immutable replay from attested-head evidence, but some replay flows still depend on process-local bundle-derived cache state to recover DSSE payload facts needed for predecessor proof and Event Log 0 baseline handling. That is acceptable as an implementation compatibility layer, but it is not a strong external audit boundary because a verifier cannot independently tell which history facts came from Rekor materialization and which came from local reconstruction.

This change is cross-cutting because it affects immutable replay materialization, exported evidence boundaries, CLI/operator reporting, tests, and trusted-log documentation. It also sits on a trust-boundary seam: if the verifier accepts cache-only historical facts as proof truth, the system's public audit story becomes weaker even if local verification remains convenient.

## Goals / Non-Goals

**Goals:**
- Make verifier-critical historical facts depend on Rekor-auditable materialization rather than process-local cache truth.
- Preserve exported attested-head evidence as the current-head attestation surface, not a replacement carrier for historical replay facts.
- Make operator output explicit about which verification facts come from public replay and which come from evidence-backed current-head binding.
- Add cache-cleared and cross-process coverage that prevents regressions back to cache-assisted proof truth.

**Non-Goals:**
- Redesign the reservation-backed predecessor contract or replace `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`.
- Expand the v1 evidence package into a full historical replay bundle.
- Remove every local cache optimization from the Sigstore adapter if the cache can remain a non-authoritative performance helper.
- Perform broader legacy-linkage cleanup beyond what is required to enforce the new verifier boundary.

## Decisions

### Decision: Rekor-materialized replay entries are the only acceptable proof source for historical continuity

The verifier will treat historical facts such as Event Log 0 baseline origin, signed predecessor continuity, and signer-linked replay material as proven only when they can be recovered from Rekor-auditable materialization. Process-local cache may still memoize or accelerate entry fetching, but cache-only facts cannot upgrade a replay result to verified history.

Alternatives considered:
- Keep bundle-derived cache as proof truth: rejected because it weakens the external audit boundary and makes public verification dependent on producer-side process state.
- Move historical replay facts into exported evidence: rejected because it collapses the distinction between public history proof and current-head attestation.

### Decision: Exported evidence remains a narrow current-head binding contract

The evidence package continues to bind `chain_id`, `sequence_num`, `head_log_id`, and `mr_value` to quote-backed state. Historical baseline and predecessor facts remain outside the evidence package and must continue to come from Rekor replay.

Alternatives considered:
- Add Event Log 0 baseline fields to evidence: rejected because it duplicates epoch-origin facts that belong to public replay.
- Add predecessor proof facts to evidence: rejected because it would let evidence obscure whether history is actually publicly auditable.

### Decision: Operator output must expose provenance, not just outcome

The CLI and structured verification result should expose whether a replay verdict is based on publicly auditable Rekor materialization, on evidence-backed current-head binding, or on unsupported cache-assisted reconstruction. This preserves a clear audit narrative even when replay is degraded or unsupported.

Alternatives considered:
- Document the distinction only in prose: rejected because operators need machine-readable and terminal-visible provenance, not just architecture notes.

### Decision: Cache-cleared tests are a release gate for this boundary

Regression coverage should exercise replay after clearing in-process bundle caches and, where practical, across fresh verifier instances. The change is not complete if the main verification path only passes when submission and replay share process-local state.

Alternatives considered:
- Keep live public-Rekor coverage best-effort only: rejected because the boundary under change is specifically about public auditability without shared process state.

## Risks / Trade-offs

- [Risk] Public Rekor materialization may not expose every predicate field in the shape currently expected by the replay normalizer. → Mitigation: explicitly define the minimum verifier-critical fact set and fail or degrade when that set cannot be recovered from public materialization.
- [Risk] Tightening provenance rules may make some currently passing smoke paths become degraded or unsupported. → Mitigation: update CLI/reporting semantics and documentation before implementation lands so the new behavior is interpretable.
- [Risk] Evidence and replay boundaries could drift if future contributors add convenience fields to the evidence package. → Mitigation: encode the boundary in the attested-head-evidence spec and add validation/tests that keep replay-only facts out of the package contract.
- [Risk] Removing cache truth abruptly may create performance regressions or additional Rekor fetches. → Mitigation: allow cache to remain as a fetch optimization as long as it does not introduce non-public proof facts.

## Migration Plan

1. Update specs to define the provenance boundary for immutable replay, evidence, and CLI reporting.
2. Refactor replay materialization so cache-derived data is treated as an optimization or unsupported fallback rather than proof truth.
3. Update CLI JSON and text reporting to distinguish public replay proof from evidence-backed current-head binding.
4. Expand unit and real-Rekor integration coverage to run with cleared cache or fresh verifier process state.
5. Update trusted-log architecture, verification, and testing docs to reflect the new external audit boundary.

Rollback strategy: restore the prior cache-assisted replay behavior behind current semantics if public materialization proves insufficient, but do not archive this change until specs and tests clearly record that fallback as non-authoritative.

## Open Questions

- What is the smallest mandatory set of historical facts that must be recoverable from Rekor materialization for a replay result to count as publicly auditable?
- Can the current Sigstore/Rekor retrieval path materialize that fact set directly, or does it need a stricter normalization contract around fetched DSSE entries?
- Should unsupported cache-assisted replay be reported as `degraded`, `unsupported`, or a new provenance-specific classification in operator output?