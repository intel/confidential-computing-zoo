## Context

The repository now documents a long-term remote verification model in which `tc-verify` consumes Rekor history plus exported attested head evidence, instead of relying on live TruCon APIs as the primary verifier input. That direction is documented in `docs/architecture.md` and `docs/trusted-log/verification.md`, but the evidence package itself is still only described at a high level.

`GAP-17A` exists to freeze the first contract for that package before any export endpoint or verifier integration is implemented. The design has to be narrow enough for one change cycle and specific enough that follow-on work can share a single schema, fixture shape, and validation model.

Constraints:

- The current deployment target is TDX RTMR[2] only.
- Event Log 0 already anchors the chain epoch in Rekor and should not be duplicated into a second baseline mechanism.
- Remote operators may not have CVM login access, so exported evidence must stand on its own when combined with Rekor replay.
- `GAP-17A` should not define the TruCon export endpoint shape or the full `tc-verify` CLI UX; those belong to `GAP-17B` and `GAP-18`.

## Goals / Non-Goals

**Goals:**

- Freeze a v1 attested head evidence schema that TruCon, `tc-verify`, and tests can share.
- Resolve the minimum quote-backed binding needed to tie a public chain head to current CVM state.
- Define canonical serialization and validation rules for required and optional fields.
- Make the relationship between Event Log 0, current head evidence, and Rekor replay explicit.

**Non-Goals:**

- Implement a TruCon evidence export endpoint or file output surface.
- Implement `tc-verify` evidence consumption or attested-head verdict logic.
- Redesign Event Log 0 contents or Rekor payload structure.
- Generalize beyond TDX or add multi-epoch stitching in this change.

## Decisions

### 1. Freeze a JSON envelope with versioned top-level fields

The v1 evidence package will be a JSON object with these required top-level fields:

- `version`
- `tee_type`
- `chain_id`
- `sequence_num`
- `head_log_id`
- `mr_value`
- `generated_at`
- `quote`
- `report_data_binding`

Optional top-level fields:

- `head_event_digest`
- `quote_format`
- `expires_at`
- `extensions`

Rationale:

- A versioned envelope gives TruCon and `tc-verify` a stable interchange contract.
- `generated_at` is required because remote verification needs a clear freshness timestamp even before a stricter TTL policy is implemented.
- `tee_type` is required even though v1 is TDX-only so the contract is self-describing and future parsing does not have to infer the quote family indirectly.

Alternatives considered:

- Minimal unversioned JSON: rejected because later field evolution would be ambiguous.
- Binary quote blob plus side-channel metadata: rejected because fixtures and validators would be harder to share across components.

### 2. Quote binding in v1 must cover chain identity, head position, and measured state

`Q-06` is resolved for v1 as follows: the quote-backed binding must cover `chain_id`, `sequence_num`, `head_log_id`, and `mr_value`.

The package will represent that through `report_data_binding`, which records:

- `algorithm`: the digest algorithm used to derive the bound value
- `bound_fields`: ordered list of fields included in the binding
- `expected_value`: the canonical digest value expected to appear in the quote-bound report data

Rationale:

- `chain_id` prevents a detached quote from being replayed across chains.
- `sequence_num` and `head_log_id` tie the evidence to a specific public chain head position.
- `mr_value` ties the evidence to the measured RTMR[2] state that should correspond to that head.

Alternatives considered:

- Bind only `head_log_id`: rejected because it omits local sequence position and measured state.
- Bind full record payloads directly into the quote: rejected because that duplicates Rekor replay responsibility and makes the contract unnecessarily heavy.

### 3. Event Log 0 stays the epoch anchor and remains outside the exported head package

The exported evidence package will not duplicate `baseline_rtmr`, `ccel_digest`, or Event Log 0 payload data. External verification must continue to obtain epoch-baseline information from Rekor replay of Event Log 0.

Rationale:

- Event Log 0 already anchors chain origin publicly.
- Duplicating baseline material into current-head evidence would create two competing sources of truth.

Alternatives considered:

- Embed Event Log 0 fields into every evidence package: rejected because it weakens source separation and adds avoidable drift risk.

### 4. Contract scope includes validation rules and fixture shape, not transport

`GAP-17A` will freeze field semantics, canonical JSON serialization expectations, and fixture examples used by tests. It will not freeze whether `GAP-17B` exposes evidence via HTTP, file export, or another read-only transport.

Rationale:

- The team needs one schema before implementing producers and consumers.
- Transport can still be chosen independently in the next change without rewriting the contract.

## Risks / Trade-offs

- [Risk] The v1 binding may omit a field later found necessary for quote verification. → Mitigation: make `report_data_binding.bound_fields` explicit and version the envelope so v2 can extend without silently changing v1 semantics.
- [Risk] Requiring `tee_type` and `generated_at` adds fields beyond the current minimum note in docs. → Mitigation: keep them as metadata-only additions that simplify validation without changing the core trust model.
- [Risk] Freezing JSON structure before transport details may still leave endpoint-level ambiguity. → Mitigation: treat transport as an explicit non-goal here and require `GAP-17B` to reuse the exact schema unchanged.

## Migration Plan

1. Add the v1 evidence contract to OpenSpec and trusted-log documentation.
2. Add shared schema/model definitions and validation fixtures without exposing a new export surface yet.
3. Implement `GAP-17B` against the frozen schema.
4. Implement `GAP-18` to consume the same schema in `tc-verify`.

Rollback is low risk because this change only freezes a contract and supporting validation artifacts. If the contract proves insufficient, a follow-up change should version it rather than mutate the v1 meaning in place.

## Open Questions

- Should `expires_at` remain optional in v1 or become mandatory once `GAP-17B` chooses an export transport?
- Should `head_event_digest` become required for operator diagnostics even if `head_log_id` and `sequence_num` remain the trust-critical binding fields?
- Which quote encoding should be treated as canonical in tests: raw base64 quote only, or a typed wrapper that also records collateral metadata?