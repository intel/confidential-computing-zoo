## Why

Docktap now has a documented daemon-internal phase taxonomy, but mixed Docker traces still treat containerd task transitions as narrative examples rather than as a normalized observation contract. The project needs that contract now so later work on API/internal correlation and healthcheck interpretation can build on stable task-transition language instead of re-deriving meaning from raw debug lines.

## What Changes

- Define a documentation-first normalized observation contract for containerd task transitions that appear in mixed Docker traces.
- Establish the minimum canonical transition set for the first version: `tasks/create`, `tasks/start`, `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit`.
- Document the minimum daemon/internal identifiers used to describe normalized task transitions, including container ID, exec ID when available, topic, timestamp, and source namespace.
- Distinguish container-task transitions from exec-task transitions while keeping both inside the existing daemon/internal `task lifecycle` phase family.
- Define which transitions are required for cold-start interpretation versus which remain supplemental for richer runtime analysis.
- Explicitly defer API/internal correlation rules, healthcheck-vs-foreground interpretation, attach-stream modeling, and parser or ingestion implementation to later GAP-22 tasks.

## Capabilities

### New Capabilities
- `daemon-task-transition-normalization`: Defines the documentation contract for normalizing containerd task transitions in mixed Docker traces without introducing cross-plane correlation or parser implementation requirements.

### Modified Capabilities
- None.

## Impact

- Affected docs: `docs/docktap/architecture.md`, `docs/docktap/api.md`, `docs/overview_tasks.md`, and related mixed-trace/runbook material.
- Affected systems: operator interpretation of mixed Docker traces and future GAP-22 planning for API/internal correlation and healthcheck/attach analysis.
- Dependencies: builds on the `daemon-internal-phase-taxonomy` capability and uses `openclaw-docker-analysis.md` as the first-source example set while leaving current Docktap code paths and HTTP API classification behavior unchanged.
