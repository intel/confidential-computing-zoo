## Context

Docktap now documents daemon/runtime-internal phases as a second observation plane alongside HTTP API request classification. That taxonomy gives mixed Docker traces a stable top-level vocabulary, but containerd task transitions such as `topic=/tasks/create`, `topic=/tasks/start`, `topic=/tasks/exec-added`, `topic=/tasks/exec-started`, and `topic=/tasks/exit` are still represented only as raw examples and ad hoc narrative interpretation.

`GAP-22.2` sits directly after taxonomy definition and directly before the later work on API/internal correlation, healthcheck interpretation, and attach-stream modeling. The design therefore needs to define a normalized observation contract for task transitions without turning this change into a parser design, ingestion plan, or cross-plane correlation spec.

## Goals / Non-Goals

**Goals:**
- Define a documentation-level normalized observation contract for containerd task transitions in mixed Docker traces.
- Establish the minimum first-wave transition set: `tasks/create`, `tasks/start`, `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit`.
- Define the minimum canonical daemon/internal facts used to describe those transitions: topic, timestamp, source namespace, container identity, and exec identity when available.
- Distinguish container-task transitions from exec-task transitions while keeping both inside the existing `task lifecycle` daemon/internal phase family.
- Define which transitions are required for cold-start interpretation versus which remain supplemental for richer runtime analysis.
- Preserve a clean boundary so later GAP-22 work can separately define API/internal joins, healthcheck interpretation, and attach/stream semantics.

**Non-Goals:**
- Define a concrete parser, ingestion surface, or runtime adapter implementation for daemon/internal task events.
- Specify API-path to task-transition correlation keys, fallback heuristics, or unified mixed-trace timeline rules.
- Define healthcheck-vs-foreground exec disambiguation.
- Define normalized attach-stream begin/end semantics.
- Define housekeeping anomaly guidance or task-exit business meaning beyond the existence of the runtime transition itself.

## Decisions

### Decision: Normalize task transitions as documentation facts, not parser output
`GAP-22.2` will define what normalized task-transition observations mean in documentation before any implementation surface exists.

- Alternative considered: define a parser-oriented event schema now.
- Why not: that would implicitly choose ingestion and implementation shapes before the project has resolved cross-plane joins or the source collection surface.

### Decision: Treat topic semantics as the stable input, not raw log templates
The contract will normalize containerd task transitions from stable topic semantics rather than from exact free-text log message templates.

- Alternative considered: catalog exact daemon log lines as the normalization contract.
- Why not: message wording is less stable than the runtime transition meaning represented by the task topic.

### Decision: Keep normalization inside the daemon/internal plane
The normalized contract will define only daemon/internal facts for task transitions and will not introduce HTTP request IDs, Docktap operation IDs, or parent-link rules.

- Alternative considered: include provisional correlation hints so mixed traces feel more complete.
- Why not: that would overlap directly with `GAP-22.3`, which is already reserved for API/internal correlation rules.

### Decision: Use one task-lifecycle family with container-task and exec-task sub-shapes
Container task transitions (`tasks/create`, `tasks/start`) and exec task transitions (`tasks/exec-added`, `tasks/exec-started`, `tasks/exit`) will be modeled as one normalized family with distinct sub-shapes rather than as separate top-level buckets.

- Alternative considered: split exec transitions into an independent family because they often appear in healthcheck flows.
- Why not: `GAP-22.1` already fixed `task lifecycle` as the top-level family, and healthcheck interpretation remains later work.

### Decision: Define a minimal required transition set for cold-start interpretation
The first normalized contract will treat `tasks/create` and `tasks/start` as the required cold-start task transitions, while exec-related transitions remain supplemental for richer runtime interpretation.

- Alternative considered: require the full task and exec sequence for all minimal analyses.
- Why not: cold-start interpretation should not depend on later runtime or healthcheck activity.

### Decision: Keep task-exit meaning narrow in the first contract
`tasks/exit` will be normalized as a runtime transition but will not be assigned health, success, or anomaly meaning in this change.

- Alternative considered: define exit success/failure interpretation now.
- Why not: exit interpretation depends on later healthcheck and attach-flow modeling and would blur the boundary with `GAP-22.4`.

## Risks / Trade-offs

- [A documentation-first contract may feel abstract without parser output] → Anchor the contract in representative examples from `openclaw-docker-analysis.md` and keep each normalized transition tied to concrete trace evidence.
- [The minimal canonical facts may later prove incomplete] → Keep the first contract intentionally small and allow later GAP-22 work to extend field guidance without redefining the initial vocabulary.
- [Readers may assume normalized transitions already imply cross-plane joins] → State explicitly that API/internal correlation remains deferred to `GAP-22.3`.
- [Healthcheck-driven exec flows may still be over-interpreted] → Keep exec-transition normalization separate from healthcheck intent and defer interpretation to `GAP-22.4`.

## Migration Plan

1. Add a new spec for normalized daemon/internal task-transition documentation.
2. Update Docktap architecture and API documentation to define the first-wave normalized transition set and minimum canonical facts.
3. Add representative mixed-trace examples from `openclaw-docker-analysis.md` for container-task and exec-task transitions.
4. Keep all runtime code paths, request classification behavior, and trusted-event emission unchanged.
5. If the contract proves confusing, roll back by removing the new documentation and capability spec without affecting runtime behavior.

## Open Questions

- Should later parser-facing work preserve the raw topic strings as canonical names, or introduce more abstract normalized transition identifiers?
- Is `namespace` part of the permanent minimal fact set, or only first-source evidence from the current OpenClaw trace?
- When additional mixed traces are analyzed, what threshold should trigger new subcategories under the task-transition model rather than additional examples inside the same first-wave contract?
