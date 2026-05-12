## Context

The repository already defines a v1 attested-head evidence contract and a remote verification architecture in which external verifiers rely on Rekor replay plus exported attested evidence. What is missing is the producer side: TruCon still exposes only operational control APIs such as `/chain-state/{chain_id}` and `/verify-chain/{chain_id}`.

This change is the producer half of that architecture. It should stay narrow: one read-only HTTP surface, one strict export policy, one quote acquisition path, and one binding-generation rule. The goal is to make later `tc-verify` evidence input work possible without broadening scope into file export, fallback UX, or full verifier behavior.

Constraints:

- v1 remains TDX RTMR[2]-only.
- Export must reuse the frozen `attested-head-evidence` contract from the archived `attested-head-evidence-contract` change.
- Export should serve remote verification, not internal mutable control-plane behavior.
- User direction for this change is explicit: HTTP only, strict export, TruCon-owned quote acquisition via configfs TSM, and latest confirmed public head only.

## Goals / Non-Goals

**Goals:**

- Expose a read-only TruCon HTTP endpoint that returns a v1 attested-head evidence package.
- Ensure export targets only the latest confirmed public head for a chain.
- Have TruCon obtain quote material directly and populate the evidence package in one place.
- Define how `expected_value` is computed from canonical bound fields prior to quote comparison.
- Make failure modes explicit when no confirmed head exists or quote acquisition/binding validation fails.

**Non-Goals:**

- File export or offline bundle packaging.
- Multi-head selection or arbitrary historical evidence export.
- `tc-verify` CLI consumption of exported evidence.
- Degraded or best-effort export for pending-only chains.
- Non-TDX quote providers or abstract attestation backends.

## Decisions

### 1. TruCon exposes one read-only HTTP surface

TruCon will expose a single read-only endpoint for evidence export, using a chain-scoped path consistent with existing read APIs.

Chosen direction:

- `GET /evidence/{chain_id}`

Rationale:

- Fits current TruCon path style (`/chain-state/{chain_id}`, `/verify-chain/{chain_id}`).
- Keeps operator-facing evidence retrieval separate from mutation surfaces.
- Avoids introducing file export workflow complexity into the producer change.

Alternatives considered:

- File export only: rejected because it adds handoff workflow design before the underlying producer surface exists.
- Multiple endpoints for head selection or status probing: rejected because v1 only needs one strict export path.

### 2. Export is strict and head selection is fixed to the latest confirmed public head

The endpoint will export evidence only for the latest confirmed immutable-log head of the requested chain.

Strict failure cases include:

- no chain exists
- chain exists but has no confirmed `head_log_id`
- chain has only pending local state
- quote acquisition fails
- quote-backed binding validation fails before response assembly

Rationale:

- Remote verification needs a stable public anchor, not a provisional local head.
- Strict behavior keeps `GAP-18A` and `GAP-18B` simpler because they will not need to interpret degraded export states.

Alternatives considered:

- Best-effort export of pending local heads: rejected because it weakens the public-chain association guarantee.
- Caller-selectable historical head: rejected as unnecessary complexity for v1.

### 3. TruCon owns quote acquisition via configfs TSM

TruCon will read quote material directly using the TDX configfs TSM interface during export.

Rationale:

- Keeps evidence production local to the component that already owns chain state.
- Avoids introducing an additional quote broker abstraction in v1.
- Matches the user-selected direction for the next step.

Alternatives considered:

- External quote helper service: rejected as unnecessary indirection for the current deployment model.
- Cached quote reuse: rejected for v1 because freshness semantics would become ambiguous immediately.

### 4. TruCon computes `expected_value`; the quote proves endorsement

`report_data_binding.expected_value` is computed by TruCon from canonical serialization of the bound fields in this exact order:

1. `chain_id`
2. `sequence_num`
3. `head_log_id`
4. `mr_value`

The quote is then used to prove that the TEE endorsed that derived binding value via report-data comparison.

Rationale:

- Keeps contract generation deterministic and producer-owned.
- Avoids treating the quote as the source of contract meaning.
- Cleanly separates “what value should be bound” from “what value the TEE attested to”.

Alternatives considered:

- Derive `expected_value` from the quote itself: rejected because the quote is evidence to compare against, not the canonical source for the binding target.
- Bind additional fields such as Event Log 0 payloads: rejected because that duplicates the baseline role of Rekor replay.

## Risks / Trade-offs

- [Risk] Strict export may frustrate operators when a chain has only pending records. → Mitigation: return explicit failure semantics and keep pending/degraded handling for later verifier UX work instead of weakening producer guarantees.
- [Risk] Direct configfs TSM quote acquisition could be environment-sensitive. → Mitigation: keep the provider choice explicit in docs and cover quote-acquisition failures in tests.
- [Risk] A single endpoint path may need reshaping later if operator workflows expand. → Mitigation: keep the evidence contract stable and treat path evolution as transport-level change, not contract change.

## Migration Plan

1. Add the read-only TruCon export endpoint and evidence assembly flow using the existing v1 contract.
2. Add tests covering successful export, missing confirmed head, and quote/binding failure cases.
3. Update verification docs to describe strict export behavior and latest-confirmed-head semantics.
4. Follow with `GAP-18A` so `tc-verify` can consume the exported evidence directly.

Rollback is straightforward: the endpoint is additive and read-only. If the export path proves unstable, it can be disabled or revised without changing existing commit or verification flows.

## Open Questions

- Should the endpoint response include any non-contract diagnostics beyond the evidence package itself, or should all diagnostics remain in HTTP status/error bodies?
- Should `expires_at` remain optional in the returned package until verifier-side freshness policy is implemented?