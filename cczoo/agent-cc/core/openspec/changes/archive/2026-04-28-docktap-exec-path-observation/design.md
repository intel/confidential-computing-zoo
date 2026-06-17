## Context

Docktap's current classifier recognizes lifecycle paths such as `create`, `start`, `stop`, and `rm`, plus a limited set of read-only observations. After completing `container_list`, the next obvious runtime-observation gap is Docker exec traffic: `POST /containers/{id}/exec` currently falls into generic container-scoped behavior, while `POST /exec/{id}/start` is not represented as a first-class observation. That makes minimal healthcheck-style flows hard to read in proxy logs and pushes high-frequency runtime activity into ambiguous buckets.

This change remains narrowly scoped to HTTP proxy observations. It does not attempt to infer daemon-internal phases, distinguish healthcheck intent from foreground exec intent, or redesign the broader observation taxonomy.

## Goals / Non-Goals

**Goals:**
- Classify `POST /containers/{id}/exec` as `exec_create`.
- Classify `POST /exec/{id}/start` as `exec_start`.
- Preserve minimal object identity for these observations so container and exec correlation stay possible in logs.
- Keep lifecycle submission and parent-linking behavior unchanged.
- Call out any intentionally deferred exec-adjacent endpoints in docs and specs.

**Non-Goals:**
- Reclassify `GET /exec/{id}/json` or other optional follow-up exec inspection paths.
- Infer whether an exec flow came from Docker healthchecks versus foreground operator activity.
- Introduce daemon-internal correlation rules for `exec-added`, `exec-started`, or `exit` phases.
- Expand streaming timeout policy or hijack semantics in this change.

## Decisions

### Decision: Use two explicit operation types: `exec_create` and `exec_start`

The classifier will use exactly two new read-only observation labels for the primary Docker exec API flow.

- Alternative considered: keep one generic `exec` bucket.
- Why not: it collapses create/start boundaries and loses the structure needed for minimal trace interpretation.

### Decision: Scope the change to the two primary exec API paths

This change covers only `POST /containers/{id}/exec` and `POST /exec/{id}/start`.

- Alternative considered: include `GET /exec/{id}/json` and related follow-up paths.
- Why not: it broadens the change into adjacent taxonomy design and is explicitly acceptable to defer under `GAP-21.2`.

### Decision: Preserve minimal stable identifiers without changing lifecycle routing

`exec_create` observations should retain the target `container_id`, and exec-path handling should preserve any available `exec_id` once Docker returns it. `exec_start` observations should retain the `exec_id` encoded in the path.

- Alternative considered: classify the paths without retaining extra exec identity.
- Why not: that would produce labels with weak forensic value and make later correlation harder than necessary.

### Decision: Keep exec observations outside `SUBMITTABLE_OPERATIONS` and lifecycle parent chains

Exec observations remain read-only proxy metadata. They do not alter the existing `pull/create/start/stop/rm` chain semantics and do not create new TruCon submissions.

- Alternative considered: attach exec flows beneath container lifecycle chains.
- Why not: the current trusted-event boundary is explicitly narrower, and this proposal is about observability rather than lifecycle control semantics.

### Decision: Defer streaming-policy changes and healthcheck interpretation

The proposal treats classification and identifier retention as sufficient for this step. Streaming behavior and daemon-internal interpretation stay out of scope.

- Alternative considered: extend streaming endpoint policy to `exec_start` immediately.
- Why not: that mixes transport-behavior changes into a classification gap and increases implementation risk for a still-narrow observation change.

## Risks / Trade-offs

- [Exec labels may still look incomplete without daemon-side context] → Document that healthcheck-vs-foreground interpretation is deferred to `GAP-22.4`.
- [Deferred `GET /exec/{id}/json` could leave some traces partly ambiguous] → Make the defer boundary explicit in docs so ambiguity is intentional rather than accidental.
- [Minimal identifier retention may require response-aware handling] → Keep the requirement narrow: preserve identifiers when already available from path or response, without introducing a new persistence model.
- [Users may expect exec traffic to influence trusted-event submission] → Reassert in proposal, spec, and docs that `SUBMITTABLE_OPERATIONS` is unchanged.

## Migration Plan

1. Add explicit exec-path classification and focused tests for the minimal create/start flow.
2. Update docs to separate exec observation labels from lifecycle commit labels and to document the deferred endpoints.
3. Leave TruCon submission, lifecycle parent-linking, and daemon-internal interpretation unchanged.
4. Roll back by removing the explicit exec labels if downstream tooling cannot absorb them, without affecting request forwarding behavior.

## Open Questions

- Should a future follow-up reuse `exec_create` / `exec_start` naming if other runtimes expose similar in-container execution APIs?
- When `GET /exec/{id}/json` is eventually added, should it become `exec_inspect` or fit under a broader exec metadata scheme?