## Context

The reservation-backed replay contract established signed predecessor truth for new records, but the read path still has a gap between protocol truth and public verification behavior. `TrustedLogAPI.verify_record()` and the Sigstore-backed immutable log adapter can prove predecessor continuity only when the predecessor entry is available through process-local replay cache behavior. That means the current implementation can validate the signed contract in local or same-process replay scenarios, but it does not yet define a complete public replay contract for candidate discovery, normalization, ambiguity handling, or operator-facing diagnostics.

This change is cross-cutting because the missing behavior spans three distinct surfaces that must agree on vocabulary and semantics:

- immutable-backend replay in `tlog-chain-verification`
- TruCon local chain verification in `trucon-chain-verification`
- operator-facing rendering in `chain-verification-cli`

The design goal is not to redesign the reservation-backed write path. Instead, it is to complete the public verification contract around that write path so replayable records can be validated from immutable-backend data without relying on backend-assigned predecessor identifiers or process-local cache accidents.

## Goals / Non-Goals

**Goals:**
- Define a stable predecessor candidate pipeline for immutable replay: discovery, materialization, matching, and verdict.
- Make immutable replay distinguish lookup failure, decode failure, missing matches, and ambiguous matches as separate machine-readable outcomes.
- Ensure TruCon `/verify-chain/{chain_id}` exposes the same predecessor result vocabulary as immutable replay rather than inventing a separate local-only classification.
- Ensure CLI JSON and human-readable output preserve those classifications and distinguish degraded replay from invalid replay.
- Define explicit operator-facing semantics for replay regime boundaries such as legacy-to-reservation and reservation-to-legacy transitions.

**Non-Goals:**
- This design does not modify the reservation-backed write contract, intent lifecycle, or Event Log 0 signing model.
- This design does not treat Rekor lookup as authoritative protocol truth; the signed predecessor contract remains the source of truth.
- This design does not guarantee that all historical legacy chains become fully replayable under the new predecessor-proof regime.
- This design does not define a new attested-head evidence format.

## Decisions

### Use a four-stage predecessor verification pipeline

Immutable replay will treat predecessor proof as a four-stage pipeline:

1. discover raw predecessor candidates from immutable-backend lookup keyed by `prev_lookup_hash`
2. materialize those candidates into normalized replay entries
3. match normalized candidates against the signed predecessor contract
4. emit a stable predecessor verdict and supporting counts

Rationale:
- The current model compresses too many failure modes into `predecessor_ok` plus a loosely defined `candidate_count`.
- Operators and callers need to know whether replay failed because discovery returned nothing, because candidates could not be decoded, because none matched, or because more than one matched.
- This staged model keeps backend-specific retrieval concerns separate from protocol-specific proof evaluation.

Alternatives considered:
- Keep a single boolean plus free-form error text: rejected because it is too lossy for operator tooling and archive-time spec evolution.
- Expose backend-native entry bodies directly to callers: rejected because it couples public diagnostics to one immutable backend representation and bypasses replay normalization.

### Standardize on `status` for categorical verdicts and `ok` for booleans

Per-entry proof output will use `predecessor_ok` for boolean or tri-state success and `predecessor_status` for categorical verdicts such as `origin`, `proven`, `missing`, `ambiguous`, `unverifiable`, `lookup_failed`, and `decode_failed`. Candidate pipeline counts will use `candidate_count`, `materialized_candidate_count`, and `matched_candidate_count`.

Rationale:
- Previous discussion exposed naming drift between `status`, `state`, and `class`.
- Using `ok` strictly for boolean-style verdicts and `status` strictly for categorical verdicts keeps JSON output consistent across replay, TruCon, and CLI layers.
- Using count-based names for pipeline stages makes ambiguity and partial decode outcomes measurable without encoding them into prose.

Alternatives considered:
- Use `state` or `class` for categorical results: rejected because they overlap with broader workflow and UI terminology and make schema reading harder.
- Use `filtered_candidate_count`: rejected in favor of `matched_candidate_count`, which is clearer to operators and closer to the proof outcome.

### Keep candidate normalization as the proof boundary

Immutable-backend predecessor proof will be evaluated only against normalized replay entries, not against raw Rekor or backend-native entry bodies. Candidate-detail output, when present, will be limited to normalized factual fields such as `entry_id`, `chain_id`, `sequence_num`, `digest`, `payload_hash`, and decode diagnostics.

Rationale:
- Replay proof depends on protocol fields, not on backend transport representation.
- A normalization boundary allows future immutable backends to share the same proof logic and caller-facing result model.
- Restricting candidate detail to normalized facts avoids locking the CLI and TruCon APIs to Rekor-specific payload shape.

Alternatives considered:
- Let each caller inspect backend-native bodies and infer proof state itself: rejected because it duplicates logic and creates inconsistent diagnostics.

### Treat replay regime boundaries as first-class operator outcomes

Verification output will classify replay regime boundaries separately from ordinary predecessor mismatch. The operator-facing result model will distinguish at least the following classes:

- `supported` for chains or chain segments that begin at a reservation-backed Event Log 0 and remain within one predecessor-proof regime
- `degraded` or `unsupported` for legacy-to-reservation boundaries where predecessor proof cannot be completed under one continuous signed contract
- `invalid` for reservation-to-legacy regressions that violate deployment expectations after a chain has entered the reservation-backed proof regime

Rationale:
- A mixed-format boundary is not the same as “the predecessor proof for one record is false”.
- Operators need to know whether the system is in an incomplete migration state or in a protocol-invalid state.
- This prevents CLI and local verification from overstating certainty when a chain spans incompatible proof regimes.

Alternatives considered:
- Fold all boundary issues into ordinary predecessor failure: rejected because it hides rollout and migration semantics that matter operationally.

### Reuse the immutable replay vocabulary in TruCon and CLI

TruCon `/verify-chain` and CLI rendering will consume the same replay verdict vocabulary rather than layering different names on top of immutable replay. TruCon remains responsible for local structural verification and CLI remains responsible for operator presentation, but both should expose the same predecessor result words and count semantics.

Rationale:
- Divergent vocabularies would create unnecessary translation layers and make troubleshooting harder.
- The replay contract should have one meaning across machine output, local verification, and CLI summaries.

Alternatives considered:
- Let each layer define its own names as long as free-form text explains them: rejected because it undermines schema stability and automation.

## Risks / Trade-offs

- [Public candidate discovery may still be backend-limited] -> Keep protocol truth in signed fields and specify discovery as candidate retrieval rather than as proof truth.
- [More output fields increase caller complexity] -> Keep the naming system disciplined: `ok` for boolean verdicts, `status` for categories, and `count` for pipeline metrics.
- [Mixed-format boundary policy may be disputed operationally] -> Specify the minimum machine-readable classes now and allow rollout posture to evolve without renaming core fields.
- [TruCon and CLI could diverge from immutable replay over time] -> Put the vocabulary into modified specs for all three capabilities in the same change.
- [Candidate-detail output could leak backend-specific structure] -> Limit candidate detail to normalized replay facts and diagnostics.

## Migration Plan

1. Extend immutable replay requirements to define the candidate pipeline, normalized proof boundary, and predecessor verdict vocabulary.
2. Extend TruCon verification requirements so `/verify-chain` returns the same predecessor categories and candidate pipeline counts for replayable records.
3. Extend CLI requirements so JSON and text output preserve those fields and distinguish degraded replay from invalid replay.
4. Implement the shared vocabulary in adapter, replay client, TruCon response serialization, and CLI rendering.
5. Add or expand tests for candidate discovery failure, candidate decode failure, no-match outcomes, ambiguity, Event Log 0 origin handling, and mixed-format boundaries.

Rollback strategy:
- The change can be rolled back by keeping the prior replay diagnostics contract, but operator tooling will remain unable to distinguish several important public replay failure modes.
- If runtime rollout is staged, new fields can be additive first, with stricter CLI interpretation enabled only after all producers of replay data expose the richer diagnostics.

## Open Questions

- Whether `boundary_status` should be emitted per entry, per replay summary, or both remains open; the change only requires a stable machine-readable boundary classification somewhere in the result model.
- Whether candidate-detail arrays should be always emitted or only when diagnostics are requested remains open.
- Whether future immutable backends need a dedicated “find candidates by payload hash” interface in `ImmutableLogAdapter` remains open, but the replay pipeline requires some backend-independent discovery abstraction.