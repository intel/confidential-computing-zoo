## Why

Docktap now documents daemon/internal phases, normalized exec-task transitions, and API/internal correlation, but mixed traces still do not explain how healthcheck-like exec flows and attach activity should be interpreted once they appear in the same timeline. The project needs that interpretation layer now so daemon-generated secondary runtime activity is not mistaken for primary workload behavior, while parser design and housekeeping guidance remain separately scoped.

## What Changes

- Define a documentation-first interpretation contract for healthcheck-like exec flows as secondary runtime activity in mixed Docker traces.
- Define how attach lifecycle lines such as `stdout/stderr begin/end` and `attach done` should be read as stream or transport activity around exec flows rather than as workload lifecycle states.
- Define the first-wave healthy healthcheck-like sequence using normalized exec-task transitions plus contextual attach and result evidence.
- Define a small first-wave anomaly surface for secondary runtime flows, such as repeated exec failures or stuck attach or exit completion.
- Keep foreground exec classification conservative by allowing healthcheck-like or secondary-runtime interpretations when evidence is incomplete.
- Explicitly defer parser implementation, machine confidence scoring, and housekeeping cleanup guidance to later GAP-22 work.

## Capabilities

### New Capabilities
- `daemon-secondary-runtime-interpretation`: Defines the documentation contract for interpreting healthcheck-like exec flows and attach or stream activity as secondary runtime behavior in mixed Docker traces.

### Modified Capabilities
- None.

## Impact

- Affected docs: `docs/docktap/architecture.md`, `docs/docktap/api.md`, `docs/overview_tasks.md`, and mixed-trace or runbook material derived from `openclaw-docker-analysis.md`.
- Affected systems: operator interpretation of mixed Docker traces and future GAP-22 planning for parser-facing healthcheck analysis, attach semantics, and anomaly handling.
- Dependencies: builds on `daemon-task-transition-normalization` and `daemon-api-internal-correlation`, reuses the existing `attach/stream` taxonomy, and leaves Docktap runtime code paths and HTTP request classification unchanged.