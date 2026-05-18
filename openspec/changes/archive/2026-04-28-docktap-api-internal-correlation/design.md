## Context

Docktap now documents two complementary observation layers for mixed Docker traces: an API-path observation plane and a daemon/internal plane with a stable taxonomy plus normalized task-transition vocabulary. What is still missing is a stable contract for relating those two planes back to each other so operators can read one mixed trace as a coherent runtime story.

`GAP-22.3` follows the taxonomy and normalization work but comes before the later healthcheck/attach and housekeeping interpretation tasks. The design therefore needs to define correlation rules across the two planes without turning this change into parser implementation, intent classification, or anomaly guidance.

## Goals / Non-Goals

**Goals:**
- Define a documentation-first correlation contract between API-path observations and normalized daemon/internal transitions in mixed traces.
- Define the primary correlation shapes for container create/start flows and exec flows.
- Define tiered join evidence, distinguishing strong identifiers from contextual evidence and fallback heuristics.
- Make one-to-many, many-to-one, and unresolved correlation states representable in documentation.
- Preserve a clean boundary so later GAP-22 work can separately define healthcheck intent, attach-stream semantics, and housekeeping guidance.

**Non-Goals:**
- Define a parser, merger engine, or ingestion implementation for building mixed timelines automatically.
- Define healthcheck-vs-foreground exec interpretation.
- Define attach-stream meaning beyond its role as optional correlation context.
- Define housekeeping anomaly rules or maintenance-signal thresholds.
- Redefine the daemon/internal taxonomy or normalized task-transition contract from GAP-22.1 and GAP-22.2.

## Decisions

### Decision: Treat correlation as an operator-facing documentation contract
`GAP-22.3` will define how mixed traces should be interpreted, not how a parser must be implemented.

- Alternative considered: define a future parser contract directly.
- Why not: implementation shape remains premature while trace sources, collection boundaries, and downstream consumers are still documentation-led.

### Decision: Correlate API observations to normalized internal transitions, not to raw log lines
The contract will use the normalized daemon/internal observations from `GAP-22.2` as the join target rather than correlating request paths straight to daemon log strings.

- Alternative considered: map API calls directly to representative raw log templates.
- Why not: the normalized layer already exists to absorb raw log variation and should remain the stable target for correlation rules.

### Decision: Use separate correlation shapes for create/start flows and exec flows
Container lifecycle joins and exec-path joins will be documented as related but distinct correlation shapes.

- Alternative considered: define one generic correlation rule for all API/internal joins.
- Why not: create/start paths primarily rely on container identity and adjacent runtime preparation, while exec paths rely more heavily on exec identity and local sequence structure.

### Decision: Tier join evidence into strong, contextual, and fallback classes
The contract will distinguish stronger identifiers such as container ID and exec ID from contextual evidence such as timestamp proximity, namespace, and operation type, and from weaker fallback heuristics such as names or adjacent runtime-prep context.

- Alternative considered: publish one flat list of possible join keys.
- Why not: a flat list would obscure which joins are canonical and which are merely helpful hints.

### Decision: Preserve ambiguous and unresolved outcomes explicitly
The contract will allow correlations to remain inferred or unresolved when trace evidence is incomplete.

- Alternative considered: force a single best match for every documented mixed-trace example.
- Why not: ambiguity is a real property of partial trace evidence and should remain representable rather than being silently over-fit.

### Decision: Leave healthcheck and attach meaning to later tasks
`GAP-22.3` may use exec-related and attach-related lines as correlation context, but it will not assign workload intent or stream semantics.

- Alternative considered: include healthcheck labeling now because exec traces in the source sample are healthcheck-heavy.
- Why not: that would overlap directly with `GAP-22.4`, which is already reserved for that interpretation layer.

## Risks / Trade-offs

- [Correlation rules may look abstract without an implementation surface] → Anchor each rule in concrete mixed-trace examples from `openclaw-docker-analysis.md`.
- [The first-source trace may bias the contract too strongly] → State explicitly that this is a first-wave documentation contract, not a claim of universal Docker/containerd trace coverage.
- [Readers may confuse heuristic joins with canonical joins] → Separate strong, contextual, and fallback evidence explicitly in docs.
- [Exec-path examples may tempt the docs into healthcheck interpretation] → Keep intent language out of this change and reserve it for `GAP-22.4`.

## Migration Plan

1. Add a new spec for API-path to daemon/internal correlation documentation.
2. Update Docktap docs to define correlation shapes for create/start and exec flows.
3. Document tiered join evidence and ambiguity handling using representative mixed-trace examples.
4. Keep runtime code, HTTP request classification, and daemon/internal normalization behavior unchanged.
5. If the correlation contract proves too broad or confusing, roll back by removing the new docs and capability spec without affecting runtime behavior.

## Open Questions

- Should later parser-facing work preserve the documentation-level evidence tiers directly, or compress them into a smaller machine-oriented confidence model?
- When additional mixed traces are analyzed, what threshold should promote a current fallback heuristic into a canonical join rule?
- Should future runbook material surface correlation outcomes as `direct`, `inferred`, and `unresolved`, or use a different vocabulary while preserving the same distinctions?
