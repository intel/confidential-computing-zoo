## Context

Docktap now has three layers for mixed Docker trace reading: a daemon/internal taxonomy, a normalized exec-task vocabulary, and a correlation contract that joins API-path observations to normalized internal transitions. What remains missing is an interpretation layer for healthcheck-like exec flows and attach activity after they have already been observed and correlated.

`GAP-22.4` sits between correlation and housekeeping guidance. The source evidence in `openclaw-docker-analysis.md` is strong for healthcheck-shaped exec flows and attach lines, but weak for foreground exec counterexamples. The design therefore needs to explain how operators should read secondary runtime activity without overcommitting to strong machine-level intent classification or pulling cleanup semantics into the same change.

## Goals / Non-Goals

**Goals:**
- Define a documentation-first interpretation contract for healthcheck-like exec flows as secondary runtime activity in mixed traces.
- Define attach lines as stream or transport context around exec flows rather than workload lifecycle states.
- Define the first-wave healthy healthcheck-like sequence using required normalized exec-task transitions plus contextual evidence.
- Define a small first-wave anomaly surface for secondary runtime flows.
- Preserve conservative language so incomplete evidence can remain healthcheck-like, inferred, or unresolved.

**Non-Goals:**
- Define a parser, merger engine, or machine confidence model for automatic intent classification.
- Guarantee binary healthcheck-versus-foreground decisions for every exec flow.
- Redefine the normalized exec-task transition contract from `daemon-task-transition-normalization`.
- Redefine API/internal correlation rules from `daemon-api-internal-correlation`.
- Define cleanup, maintenance, or housekeeping anomaly guidance.

## Decisions

### Decision: Treat `GAP-22.4` as an interpretation layer, not a new event model
The change will explain how to read already-normalized and already-correlated mixed-trace evidence rather than inventing a new event schema.

- Alternative considered: define a parser-facing healthcheck event model directly.
- Why not: current evidence is documentation-led and still too narrow for a stable machine contract.

### Decision: Use `secondary runtime activity` as the top-level interpretation bucket
The first-wave contract will primarily distinguish secondary runtime activity from primary workload lifecycle behavior, and only then allow more specific healthcheck-like interpretation when evidence supports it.

- Alternative considered: require every documented exec flow to be labeled healthcheck-driven or foreground.
- Why not: the available source trace is rich for healthcheck examples but thin for foreground exec counterexamples.

### Decision: Keep normalized exec-task transitions as the runtime spine
`tasks/exec-added`, `tasks/exec-started`, and `tasks/exit` remain the required runtime skeleton for secondary exec interpretation.

- Alternative considered: let attach begin/end lines define the primary sequence.
- Why not: attach lines are contextual transport evidence around the exec flow, not the runtime state transitions themselves.

### Decision: Model attach lines as a transport envelope around exec flows
`attach: stdout begin/end`, `attach: stderr begin/end`, and `attach done` will be documented as stream or transport phases that surround exec activity and help explain flow completion.

- Alternative considered: elevate attach lines into a parallel workload lifecycle track.
- Why not: that would blur workload state with transport behavior and compete with the existing task-lifecycle spine.

### Decision: Split evidence into required and contextual layers
The first-wave healthcheck-like sequence will require the normalized exec-task spine and treat attach lines, repeated cadence, and explicit healthcheck result lines as contextual evidence.

- Alternative considered: require all evidence to be present for a healthy healthcheck sequence.
- Why not: mixed traces are often partial, and a stricter rule would make the contract brittle.

### Decision: Keep anomaly guidance narrow and local to the secondary flow
The change will only describe small anomalous shapes such as repeated exec failures, missing exit after exec start, or missing attach completion after attach begins.

- Alternative considered: include cleanup lag, maintenance churn, or broader daemon noise thresholds now.
- Why not: those belong to housekeeping guidance in `GAP-22.5`.

## Risks / Trade-offs

- [Healthcheck interpretation may overfit the current source trace] -> Keep the contract first-wave, operator-facing, and explicit about limited evidence.
- [Readers may mistake contextual evidence for proof] -> Separate required exec-task evidence from contextual attach and result cues in both docs and specs.
- [Attach semantics may drift into workload semantics] -> State explicitly that attach lines are transport context, not workload lifecycle states.
- [Cleanup behavior may leak into this scope] -> Keep housekeeping, exec cleanup, and maintenance guidance deferred to `GAP-22.5`.

## Migration Plan

1. Add a new capability spec for secondary runtime interpretation.
2. Update Docktap architecture and API documentation to define healthcheck-like exec interpretation and attach-envelope meaning.
3. Add representative mixed-trace examples from `openclaw-docker-analysis.md` showing healthy secondary-runtime sequences and narrow anomalous shapes.
4. Update `docs/overview_tasks.md` so `GAP-22.4` reflects the interpretation-contract scope and stays separated from `GAP-22.5`.
5. Keep runtime code, request classification, and normalized transition behavior unchanged.

## Open Questions

- Should future parser-facing work preserve the documentation distinction between `secondary runtime activity` and `healthcheck-like`, or collapse them into a single confidence-scored outcome?
- What additional trace evidence would be sufficient to promote foreground exec interpretation from a deferred concern into a stronger documented distinction?
- Should attach lines eventually gain a more formal sub-vocabulary inside `attach/stream`, or remain contextual evidence around exec interpretation?