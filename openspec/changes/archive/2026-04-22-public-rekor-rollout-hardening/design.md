## Context

The signed predecessor contract is already the protocol truth for new replayable records, but the remaining public-Rekor path still has two rollout gaps. First, real Rekor coverage is still biased toward synthetic or single-step cases, so the code path that discovers candidates by `prev_lookup_hash`, materializes multiple public entries, and proves one predecessor across more than one Rekor record is not yet pinned down by an end-to-end requirement. Second, mixed-regime chains still need an explicit rollout posture so operators can tell the difference between a legacy boundary that is visible but not fully provable and a regression back into a legacy regime after a chain has already entered the reservation-backed contract.

This is a cross-cutting hardening change across immutable replay, TruCon local verification, and CLI rendering. The design stays narrow: it does not redesign the reservation-backed write path, and it does not attempt to retroactively make every historical legacy chain fully replayable under the new proof contract. It defines how rollout state is classified, how public Rekor proof is exercised against realistic data, and how those outcomes are surfaced consistently.

## Goals / Non-Goals

**Goals:**
- Require end-to-end public-Rekor tests that prove predecessor continuity across multi-entry history using the signed `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` contract.
- Define stable replay-boundary semantics for legacy-only chains, supported reservation-backed chains, and reservation-to-legacy regressions.
- Keep immutable replay, TruCon `/verify-chain`, and CLI output on one shared vocabulary for rollout-boundary and predecessor-proof outcomes.
- Make rollout guidance explicit enough that operators can decide whether a result is supported, degraded during migration, or invalid.

**Non-Goals:**
- This design does not change commit-intent reservation, DSSE signing, or Event Log 0 payload structure.
- This design does not make Rekor discovery authoritative; signed predecessor fields remain the only proof truth.
- This design does not require broad historical backfill or conversion of legacy entries.
- This design does not add a new verification profile or a new external API beyond the existing verification surfaces.

## Decisions

### Treat public-Rekor proof coverage as a rollout gate

The change will require at least one real-Rekor integration path that exercises more than one replayable record in the same chain and validates predecessor proof through public candidate discovery rather than only through synthetic fixtures or process-local cache reuse.

Rationale:
- The remaining risk is not whether the predecessor contract exists, but whether the public-Rekor path proves it under realistic multi-entry history.
- Single-entry smoke tests cannot show that `prev_lookup_hash` discovery, candidate materialization, and signed predecessor matching remain stable across chained records.

Alternatives considered:
- Continue relying on synthetic adapter fixtures only: rejected because rollout hardening specifically targets the public-Rekor path.
- Require large full-suite public integration coverage for every scenario: rejected because the proposal is intentionally narrow and should stay feasible as an opt-in integration layer.

### Classify replay boundaries separately from proof mismatches

Verification will treat replay regime boundaries as first-class rollout outcomes instead of folding them into ordinary predecessor mismatch. The model will distinguish at least three operator meanings:

- supported reservation-backed replay
- degraded or legacy-boundary replay where visibility exists but continuous predecessor proof does not
- invalid regression where a chain that already entered the reservation-backed regime later falls back to incompatible legacy linkage

Rationale:
- A legacy boundary is an operational migration fact, not necessarily evidence that one signed predecessor contract was false.
- A reservation-to-legacy regression is stronger: once a chain has entered the signed predecessor regime, falling back undermines the expected contract and should not be reported as merely degraded.

Alternatives considered:
- Treat every mixed chain as invalid: rejected because it would make staged rollout unnecessarily brittle and would misclassify known migration boundaries.
- Treat every mixed chain as degraded: rejected because it would understate regressions after a chain has already moved into the supported regime.

### Reuse one machine-readable vocabulary across replay, TruCon, and CLI

Immutable replay remains the source of structured predecessor and boundary facts. TruCon and CLI will preserve those facts rather than inventing local aliases. Boundary classification remains machine-readable, and human-readable output is derived from that shared model.

Rationale:
- Rollout hardening is mostly about reducing ambiguity during migration.
- Different names for the same boundary state would defeat that goal and create unnecessary operator translation work.

Alternatives considered:
- Let CLI convert low-level statuses into unrelated summary labels: rejected because it would weaken automation and make mixed-regime debugging harder.

### Prefer additive rollout guidance over protocol redesign

The change will add rollout requirements and tests without changing the underlying predecessor-proof contract. Legacy compatibility parsing may remain as an implementation concern, but the supported public contract is the reservation-backed signed predecessor model.

Rationale:
- The protocol transition has already happened at the truth layer.
- The remaining problem is rollout clarity and validation depth, not lack of a proof contract.

Alternatives considered:
- Remove all legacy handling as part of this change: rejected because that is a separate cleanup track and would widen scope beyond rollout hardening.

## Risks / Trade-offs

- [Real Rekor tests may be slower or more fragile than local fixtures] -> Keep them opt-in and narrowly scoped to the multi-entry proof path that synthetic tests cannot cover.
- [Boundary classifications may still leave some historical chains only partially verifiable] -> Make that state explicit as degraded rollout rather than pretending to offer full continuity proof.
- [Compatibility code may continue to exist after the supported contract has narrowed] -> Keep the spec focused on supported verification behavior, not on immediate removal of all compatibility parsing.
- [CLI messaging could drift from machine-readable output] -> Require the CLI to preserve boundary and predecessor fields in JSON and derive terminal summaries directly from those same values.

## Migration Plan

1. Add delta specs that define rollout-boundary semantics and public-Rekor multi-entry proof coverage requirements.
2. Expand immutable replay and Rekor integration tests to cover at least one multi-entry public chain with signed predecessor validation.
3. Align TruCon `/verify-chain` output so mixed-regime boundaries and regressions surface as stable machine-readable classifications.
4. Align CLI JSON and human-readable summaries with the same boundary vocabulary and rollout guidance.
5. Update testing and operator documentation once the new rollout classifications and public-Rekor test path are implemented.

Rollback strategy:
- The rollout hardening change is additive. If needed, stricter operator interpretations can be relaxed while preserving the richer machine-readable diagnostics.
- Real-Rekor integration coverage can remain opt-in if external service stability becomes an issue, but the capability should still exist and be exercised in controlled environments.

## Open Questions

- Whether the boundary vocabulary should use `supported` and `degraded` exactly, or preserve those meanings under existing status names, remains open as long as the machine-readable distinction is stable.
- Whether real-Rekor multi-entry coverage should live in one dedicated test or a small focused suite remains open.
- Whether reservation-to-legacy regression should fail only the affected entry or the whole replay result in every surface remains open, but it must be classified more strongly than an ordinary migration boundary.