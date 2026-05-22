## Why

Docktap now documents both a daemon/internal phase taxonomy and a normalized task-transition contract, but mixed Docker traces still do not have stable rules for joining API-path observations back to daemon/internal runtime activity. The project needs those correlation rules now so operators can read one mixed trace as a coherent timeline without collapsing correlation, healthcheck intent, and parser design into a single over-scoped change.

## What Changes

- Define a documentation-first correlation contract for relating proxy-observed Docker API operations to normalized daemon/internal runtime transitions in mixed traces.
- Document the primary correlation shapes for container create/start flows and exec flows rather than treating all joins as one generic rule.
- Define tiered join evidence for mixed-trace correlation, separating canonical identifiers from contextual evidence and fallback heuristics.
- Document how one API observation may correlate to multiple daemon/internal transitions and how ambiguous or unresolved correlations remain representable.
- Add representative mixed-trace correlation examples grounded in `openclaw-docker-analysis.md`.
- Explicitly defer parser implementation, healthcheck-vs-foreground exec interpretation, attach-stream semantics, and housekeeping anomaly guidance to later GAP-22 tasks.

## Capabilities

### New Capabilities
- `daemon-api-internal-correlation`: Defines the documentation contract for correlating API-path observations with normalized daemon/internal runtime transitions in mixed Docker traces.

### Modified Capabilities
- None.

## Impact

- Affected docs: `docs/docktap/architecture.md`, `docs/docktap/api.md`, `docs/overview_tasks.md`, and mixed-trace/runbook material.
- Affected systems: operator interpretation of mixed traces and future GAP-22 planning for healthcheck/attach modeling and housekeeping analysis.
- Dependencies: builds on `daemon-internal-phase-taxonomy` and `daemon-task-transition-normalization`, uses `openclaw-docker-analysis.md` as the first-source evidence set, and leaves current Docktap code paths and HTTP request classification behavior unchanged.
