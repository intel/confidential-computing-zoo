## Why

Docktap's current observability model explains Docker Engine API request paths well, but mixed traces such as `openclaw-docker-analysis.md` also contain daemon-internal phases that are currently described only as ad hoc narrative analysis. The project needs a stable taxonomy for those internal phases now so later work on normalization, correlation, and healthcheck interpretation can build on shared language instead of one-off trace readings.

## What Changes

- Define a documentation-level taxonomy for daemon/runtime-internal phases that complements the existing HTTP API request classification model.
- Establish stable top-level phase families for mount activity, runtime bundle/spec preparation, task lifecycle transitions, attach/stream activity, and housekeeping work.
- Add real mixed-trace examples showing how representative daemon log lines map into those phase families.
- Explicitly scope this change to taxonomy and examples only, deferring event normalization, API-to-internal correlation rules, healthcheck disambiguation, and anomaly guidance to later GAP-22 tasks.

## Capabilities

### New Capabilities
- `daemon-internal-phase-taxonomy`: Defines the documentation contract for classifying Docker daemon and containerd internal phases in mixed traces alongside the existing API-path observation layer.

### Modified Capabilities
- None.

## Impact

- Affected docs: `docs/docktap/architecture.md`, `docs/docktap/api.md`, and related runtime observability/runbook material.
- Affected systems: mixed Docker trace interpretation and future GAP-22 planning for task normalization, cross-plane correlation, and healthcheck/internal-runtime analysis.
- Dependencies: uses `openclaw-docker-analysis.md` as the first-source example set while leaving current Docktap code paths and API classification behavior unchanged.