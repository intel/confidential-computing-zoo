## Context

Docktap's current documentation defines an API-path observation plane centered on Docker Engine requests seen by the Unix-socket proxy, including lifecycle operations, read-only probe traffic, exec paths, and log reads. Real mixed traces such as `openclaw-docker-analysis.md` also include daemon-internal activity like overlay mounts, OCI bundle creation, containerd task transitions, attach lifecycle, and exec cleanup, but those phases are currently explained only as one-off analysis rather than through a stable project taxonomy.

`GAP-22` already splits this work into four downstream concerns after taxonomy definition: task normalization, API/internal correlation, healthcheck and attach interpretation, and housekeeping coverage. The design for `GAP-22.1` therefore needs to provide a vocabulary layer that is stable enough for later phases without prematurely turning documentation taxonomy into a parser, schema, or correlation contract.

## Goals / Non-Goals

**Goals:**
- Define a documentation-level taxonomy for daemon/runtime-internal phases that is distinct from the existing HTTP API request classification model.
- Establish stable top-level phase families for storage/mount, runtime-spec/bundle preparation, task lifecycle, attach/stream activity, and housekeeping work.
- Use representative examples from `openclaw-docker-analysis.md` to illustrate how mixed-trace lines fit those phase families.
- State explicitly that this taxonomy complements API-path observations rather than replacing them.
- Preserve room for later GAP-22 tasks to define normalization, correlation, healthcheck interpretation, and anomaly guidance separately.

**Non-Goals:**
- Define a formal ingestion schema or parser contract for daemon/internal events.
- Normalize containerd task topics into canonical event objects.
- Specify how internal phases join back to API requests, container IDs, or exec IDs.
- Introduce code changes, new event emitters, or new runtime collection surfaces.
- Promote healthcheck traffic into its own top-level phase family.

## Decisions

### Decision: Treat daemon/internal phases as a second observation plane

`GAP-22.1` will define daemon/runtime-internal phases as a documentation layer that sits alongside the existing API-path observation plane.

- Alternative considered: extend the existing `sock-bridge-lifecycle-classification` model to absorb daemon/internal phases directly.
- Why not: the current classifier is request-oriented and proxy-observed, while daemon/internal phases come from a different source plane and should stay conceptually separate.

### Decision: Fix five top-level phase families for the first taxonomy

The initial taxonomy will use five top-level families: storage/mount, runtime-spec/bundle, task lifecycle, attach/stream, and housekeeping.

- Alternative considered: keep the taxonomy open-ended and purely descriptive.
- Why not: later GAP-22 phases need a stable vocabulary; a taxonomy that stays too loose will not constrain normalization or example mapping enough.

### Decision: Model by runtime behavior, not by raw log template

The taxonomy will describe what the daemon/runtime is doing rather than treating individual log line strings as the canonical categories.

- Alternative considered: define the taxonomy directly from recurring log messages such as `bundle dir created` or `attach done`.
- Why not: message templates are useful examples, but behavior-oriented families remain more stable across minor runtime/log format variation.

### Decision: Keep healthcheck as a cross-cutting interpretation, not a phase family

Healthcheck-driven activity may appear within task lifecycle and attach/stream families, but `GAP-22.1` will not elevate healthcheck to a top-level taxonomy bucket.

- Alternative considered: add a dedicated `healthcheck` family because the source analysis prominently features healthcheck exec flows.
- Why not: healthcheck is better treated as workload intent or source context, which is the domain of later correlation and interpretation work in `GAP-22.4`.

### Decision: Use the OpenClaw daemon analysis as the first-source example set

`openclaw-docker-analysis.md` will anchor the example mappings for this change, but the taxonomy will be written as a stable interpretive layer rather than as a claim that the sample covers every daemon/internal phase.

- Alternative considered: wait for multiple trace sources before defining any taxonomy.
- Why not: the current sample already contains enough representative internal behavior to establish a first version, and deferring all vocabulary would block the rest of GAP-22.

### Decision: Defer schema, correlation, and anomaly rules explicitly

The design will call out that normalization, cross-plane joins, healthcheck-vs-foreground disambiguation, and housekeeping anomaly guidance remain future tasks.

- Alternative considered: include lightweight placeholders for field contracts and correlation keys now.
- Why not: even lightweight contracts would turn this documentation taxonomy into an implicit schema design and blur the task boundaries already established in `overview_tasks.md`.

## Risks / Trade-offs

- [A documentation-only taxonomy may feel too abstract] → Anchor each family with concrete example mappings from the existing daemon analysis.
- [The five families may later prove too coarse or too fine] → Keep the top-level families stable while allowing later GAP-22 work to add subcategories without redefining the first layer.
- [Readers may assume taxonomy implies collection or parser support] → State explicitly that this change is observational vocabulary only and introduces no ingestion contract.
- [Healthcheck flows may still be misread after taxonomy alone] → Reserve healthcheck interpretation for `GAP-22.4` and keep that defer boundary explicit in docs and specs.

## Migration Plan

1. Add the new daemon/internal taxonomy capability spec.
2. Update Docktap architecture and API documentation to introduce the second observation plane and the five top-level phase families.
3. Add example mappings drawn from `openclaw-docker-analysis.md` for each family.
4. Keep all code, event production, and API-path classification behavior unchanged.
5. If the taxonomy proves confusing, roll back by removing the new documentation sections and capability spec without affecting runtime behavior.

## Open Questions

- Should future GAP-22 work treat the five top-level families as canonical names, or only as stable documentation headings with more formal names introduced later?
- When additional daemon trace sources are analyzed, what threshold should trigger splitting one of the five families into subfamilies?
- Should the final mixed-trace documentation live primarily in `docs/docktap/architecture.md`, or should later phases factor a separate runbook-style document for operators?