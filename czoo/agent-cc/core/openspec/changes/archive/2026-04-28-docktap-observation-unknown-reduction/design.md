## Context

Docktap's observation model now distinguishes preflight requests, image inspection, container list, exec paths, and several resource-probe families. That reduced a large amount of generic `inspect` and `unknown` noise, but common read-only endpoints such as container log reads still fall into the fallback bucket. As a result, the remaining `unknown` surface is partly real defer scope and partly accidental under-classification.

This change is intended as the closing pass on the current HTTP-path observation expansion before the project moves into the daemon/internal phase work in GAP-22. The design therefore needs to improve readability without broadening trusted-event scope or pulling daemon stream lifecycle semantics into the proxy classifier.

## Goals / Non-Goals

**Goals:**
- Promote at least `GET /v*/containers/{id}/logs` from `unknown` into an explicit observation class.
- Turn the remaining `unknown` bucket into a documented and intentional boundary rather than accidental overflow.
- Keep observation-only endpoints separate from trusted lifecycle commit types.
- Preserve existing streaming timeout behavior while improving path-level classification clarity.

**Non-Goals:**
- Model attach lifecycle, stream begin/end markers, or daemon-internal phases.
- Expand `SUBMITTABLE_OPERATIONS` or reinterpret read-only observations as trusted events.
- Introduce a general-purpose multi-level taxonomy for all future read-only endpoints.
- Classify every remaining Docker Engine API endpoint that currently lands in `unknown`.

## Decisions

### Decision: Make container logs the first-wave explicit unknown-bucket reduction target

The first implementation will add an explicit operation label for `GET /v*/containers/{id}/logs` rather than trying to solve all remaining read-only endpoints at once.

- Alternative considered: classify a wide batch of read-only endpoints in one change.
- Why not: the remaining `unknown` set contains mixed-frequency and mixed-semantic paths, so a broad sweep would hide boundary decisions inside one proposal.

### Decision: Use an explicit operation type instead of a generic subtype field

Container log reads should follow the same style as `container_list`, `exec_create`, and `network_inspect` by gaining a dedicated operation label.

- Alternative considered: keep `unknown` and add a secondary `resource.kind` or `observation.kind` field.
- Why not: the current classifier contract is centered on a single canonical operation type, and changing the shape now would add unnecessary contract churn.

### Decision: Keep stream lifecycle semantics out of scope

This change only labels the API request path for log reads. It does not model follow-mode behavior, attach phases, or begin/end stream lifecycle.

- Alternative considered: combine logs classification with transport/stream phase modeling.
- Why not: those semantics belong to GAP-22's daemon/internal layer, especially the healthcheck/attach work.

### Decision: Document intentional deferrals alongside the new classifier case

The fallback `unknown` bucket remains valid, but the docs should list the intentionally deferred endpoint families that still land there after this change.

- Alternative considered: treat docs as incidental and only add the new classifier case.
- Why not: GAP-21.5 is specifically about turning `unknown` into a conscious boundary, not just shrinking it by one endpoint.

### Decision: Preserve trusted-event boundaries unchanged

The new observation class remains local observability metadata only and does not alter trusted-event submission or parent-linking rules.

- Alternative considered: treat frequent log reads as candidates for richer event emission.
- Why not: there is no new trust or lifecycle contract here, only better observation readability.

## Risks / Trade-offs

- [Only classifying logs may feel too narrow if other read-only endpoints still appear as `unknown`] → Pair the code change with explicit deferred-endpoint documentation.
- [Operators may over-read the new label as a daemon stream model] → State clearly that only HTTP-path classification changes here and attach/stream phases remain separate work.
- [Future endpoint additions may drift if no defer list is maintained] → Make the documented fallback boundary part of the spec and docs, not just incidental commentary.

## Migration Plan

1. Extend the path classifier to assign a dedicated observation label to `GET /v*/containers/{id}/logs`.
2. Add focused tests for versioned and unversioned log-read paths while preserving existing streaming behavior.
3. Update Docktap architecture/API docs to list the new explicit observation class and the intentional deferred `unknown` endpoints.
4. Roll back by removing the logs-specific label and tests if downstream tooling cannot absorb the new observation class.

## Open Questions

- Should the documented defer list in this change stay illustrative, or should it enumerate every currently known high-frequency `unknown` path?
- If a later change adds more read-only endpoints, should the naming pattern continue as explicit operation types or eventually move to a grouped observation taxonomy?