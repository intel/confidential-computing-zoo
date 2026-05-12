## Context

Docktap already classifies several read-only probe paths explicitly, including `image_inspect`, `network_inspect`, `volume_inspect`, and `plugin_inspect`. That solved the question of *what resource family Docker probed*, but not the adjacent question of *whether the probe result was a normal miss or a true error*. Today the observation model keeps only the raw HTTP status in local response metadata, while TruCon lifecycle submission uses a separate `operation_result` field that applies only to trusted lifecycle operations.

This change is the narrow follow-up to resource probe classification. It adds local observation outcome semantics for selected probe-style operations without widening trusted-event submission, changing Docker API behavior, or introducing higher-level intent inference.

## Goals / Non-Goals

**Goals:**
- Add a stable local observation outcome field that distinguishes `ok`, benign `miss`, and `error`.
- Treat `404` responses for selected probe-style observation types as normal misses.
- Keep daemon `404` responses distinguishable from proxy/local transport failures.
- Keep TruCon `operation_result` and `SUBMITTABLE_OPERATIONS` unchanged.
- Make the first wave intentionally small and explicit so later outcome coverage can extend from a stable base.

**Non-Goals:**
- Reuse or reinterpret TruCon `operation_result` for read-only observations.
- Infer request intent such as warm-container detection, reconciliation, or operator troubleshooting.
- Add benign-miss semantics to every read-only Docker endpoint.
- Treat container detail `inspect` `404` responses as benign misses in this change.
- Change Docker proxy forwarding behavior or daemon HTTP semantics.

## Decisions

### Decision: Store observation outcome in `response.outcome`

The new semantics will extend local response metadata under `OperationRecord.response` rather than adding a new top-level contract.

- Alternative considered: add a top-level `observation_result` field.
- Why not: response interpretation already lives under `response`, and a top-level field would create unnecessary contract churn.

### Decision: Use a fixed first-wave outcome set: `ok`, `miss`, `error`

The first version will use exactly three values to keep downstream interpretation simple.

- Alternative considered: richer values such as `success`, `miss`, `failed`, `retryable`, or `transport_error`.
- Why not: the current gap is about separating normal misses from generic failures, not building a complete failure taxonomy.

### Decision: `miss` applies only to explicitly listed probe-style observation types

In this change, benign `miss` handling applies to `image_inspect`, `network_inspect`, `volume_inspect`, and `plugin_inspect` when Docker returns `404`.

- Alternative considered: treat any read-only `GET` `404` as `miss`.
- Why not: that would overgeneralize and blur the line between normal probe checks and unexpected missing-object failures.

### Decision: Keep container detail `inspect` conservative

`GET /containers/{id}/json` remains outside first-wave benign miss handling even when it returns `404`.

- Alternative considered: classify container detail inspect `404` as `miss` for consistency with multi-resource name probing.
- Why not: container detail lookup is more ambiguous and can represent stale references or other real errors, so widening it now would weaken the change boundary.

### Decision: Determine outcome from `operation.type` plus response/proxy result

Outcome semantics are derived from the canonical operation type and the response source/status, not from caller identity or inferred workflow intent.

- Alternative considered: factor in request sequences or contextual intent.
- Why not: that would turn a narrow response-model change into higher-level behavioral inference.

### Decision: Proxy/local failures remain `error`

Malformed requests, socket failures, timeouts, and other proxy-local failures stay distinct from daemon-level `404` responses and always resolve to `error`.

- Alternative considered: introduce a separate `transport_error` value immediately.
- Why not: the distinction can already be preserved through status/source details without expanding the first-wave outcome vocabulary.

## Risks / Trade-offs

- [Benign miss handling may be expected on more endpoints than the first wave covers] → Keep the initial allowlist explicit and document deferred endpoints clearly.
- [Users may confuse local observation outcome with TruCon lifecycle result] → Keep the new field under `response` and reiterate that `operation_result` remains lifecycle-only.
- [Container detail `404` will still look harsher than some callers expect] → Preserve the conservative boundary now and revisit only in a later targeted change.
- [Outcome semantics can drift if new probe types are added later without rules] → Tie `miss` behavior to explicit operation types and extend via later spec changes.

## Migration Plan

1. Extend response enrichment to record a local observation outcome for selected probe-style operations.
2. Add focused tests for `ok`, benign `miss`, and `error` outcomes, including proxy/local failure separation.
3. Update architecture and API docs to distinguish local observation outcome from trusted lifecycle result.
4. Roll back by removing the new outcome field and tests if downstream consumers cannot absorb it, without changing request forwarding or trusted-event submission.

## Open Questions

- Should the first implementation also attach a stable outcome source/reason field, or is `response.status` plus `response.outcome` sufficient for now?
- When container detail `inspect` is reconsidered later, should it share the same `miss` rules or use a more specific container-inspect outcome policy?