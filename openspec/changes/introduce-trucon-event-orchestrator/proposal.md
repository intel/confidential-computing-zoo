## Why

The current trusted-log path is tightly coupled inside the existing API workflow and relies on in-process state, which becomes fragile under multi-process deployment and when Docktap runs as a separate process. We need a single core service that preserves trusted-log semantics while supporting concurrent callers from both REST API workers and Docktap workers.

## What Changes

- Introduce TruCon as a core internal service that centralizes trusted event ingestion, trusted-log submission orchestration, and runtime instance mapping.
- Keep the existing REST API architecture as the control plane for build/publish/launch lifecycle orchestration, but route trusted-log writes through TruCon boundaries.
- Add Docktap as a dedicated service process that reports runtime events to TruCon without directly mutating trusted-log chain state.
- Define durable submission lifecycle semantics for trusted events, including commit, queue, submit, retry, and confirmation states.
- Define instance-mapping capability inside TruCon to correlate workload identifiers and Docker instance identifiers with trusted events.
- Preserve compatibility expectations for existing external API behavior while introducing internal service boundaries.

## Capabilities

### New Capabilities
- `trucon-event-orchestration`: Define TruCon responsibilities and APIs for trusted event ingest, commit/submit lifecycle, queue-driven submission, and status querying.
- `trucon-instance-mapping`: Define how TruCon records and queries workload-to-instance and instance-to-event relationships across REST and Docktap sources.
- `rest-docktap-trucon-integration`: Define integration requirements so existing REST control-plane flows and Docktap process flows both publish trusted events through TruCon.

### Modified Capabilities
- None.

## Impact

- Affected systems:
  - Existing REST API service process model (control plane remains, trusted-log writes are re-routed by contract).
  - Docktap service process lifecycle and event reporting contract.
  - Trusted-log submission and verification operational paths.
- Affected internal APIs:
  - New internal TruCon service endpoints for event ingestion, submission lifecycle status, and instance mapping queries.
- Operational impact:
  - Requires clear idempotency policy, queue observability, and retry/confirmation metrics.
  - Requires deployment/runtime topology updates to include TruCon and Docktap as independent processes.
