## Context

Docktap's current operation classifier explicitly distinguishes lifecycle requests such as `pull`, `create`, `start`, `stop`, and `rm`, plus a small set of preflight and inspection paths. The implementation currently treats container-scoped paths broadly, which leaves `GET /containers/json` without a first-class observation identity even though that endpoint represents a different semantic from `GET /containers/<id>/json`.

This change is intentionally narrow. It targets one missing classification that shows up in real control-plane traces, especially `docker ps` and `docker ps -a` style scans. It does not redesign the full observation taxonomy and does not change trusted-event submission rules.

## Goals / Non-Goals

**Goals:**
- Classify `GET /containers/json` and `GET /v*/containers/json` as `container_list`.
- Preserve query parameters in structured metadata so `docker ps` and `docker ps -a` remain distinguishable.
- Keep the boundary between container-list observations and detail inspection explicit in code, tests, and docs.
- Leave lifecycle submission, parent-linking, and proxy forwarding semantics unchanged.

**Non-Goals:**
- Introduce a generic `resource_list` or multi-level observation taxonomy.
- Infer operator intent such as polling, reconciliation, or maintenance from the request alone.
- Reclassify exec, logs, stats, top, or changes endpoints.
- Expand `SUBMITTABLE_OPERATIONS` or emit new TruCon commits for list traffic.

## Decisions

### Decision: Use a dedicated canonical type named `container_list`

`GET /containers/json` will map to `container_list` rather than reusing `inspect` or adding an abstract list framework.

- Alternative considered: introduce a generic `resource_list` family.
- Why not now: that broadens the change into taxonomy redesign and is unnecessary for the current high-frequency gap.

### Decision: Match by exact list path, not by broad container prefix

The classifier will recognize only `GET /containers/json` and `GET /v*/containers/json` for this change.

- Alternative considered: classify any `/containers/*` path with query params as list-like.
- Why not: that risks bleeding into detail inspection and later exec/logs work.

### Decision: Preserve list query parameters as observation metadata

The existing query-parameter parsing path should continue to retain raw values for `all`, `limit`, `filters`, `before`, and `since` so downstream analysis can distinguish common list variants.

- Alternative considered: normalize only `all` and drop the rest.
- Why not: it would throw away useful context and create another follow-up change just to restore fidelity.

### Decision: Keep `container_list` outside lifecycle parent-linking and TruCon submission

`container_list` is a read-only observation type. It does not become part of the pull/create/start/stop/rm chain and does not alter `SUBMITTABLE_OPERATIONS`.

- Alternative considered: treat repeated list calls as operational reconciliation events.
- Why not: request-path classification alone cannot prove intent, and this change is scoped to observability rather than control semantics.

## Risks / Trade-offs

- [New operation bucket changes downstream aggregations] → Document the compatibility impact and keep semantics narrow so consumers can adjust predictably.
- [Scope creep into adjacent `/containers/*` paths] → Keep exact-path matching and defer exec/logs/stats work to `GAP-21.2` and `GAP-21.5`.
- [Loss of query fidelity if params handling changes later] → Make parameter retention an explicit requirement and cover it in focused tests.

## Migration Plan

1. Add the new classifier mapping and test coverage.
2. Update Docktap docs to describe `container_list` as a read-only observation type.
3. Leave all commit and verification flows unchanged.
4. Roll back by removing the explicit mapping if downstream tooling cannot absorb the new bucket, without affecting Docker API forwarding behavior.

## Open Questions

- Should future list-oriented endpoints such as `/images/json` follow the same one-off naming pattern or wait for a broader taxonomy change?
- Do any downstream dashboards currently treat `inspect` as a catch-all bucket in a way that should be called out in release notes?