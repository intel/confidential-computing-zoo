## Why

Docktap currently leaves Docker exec traffic split across generic container inspection and `unknown` buckets, which makes healthcheck-style execution paths and other in-container command activity difficult to interpret in proxy traces. This is the next high-frequency observation gap after `container_list`, and it can be closed without widening trusted-event submission scope.

## What Changes

- Add explicit read-only observation classifications for Docker exec API create/start paths.
- Preserve minimal object identity for exec-path observations so `container_id` and `exec_id` remain queryable in logs.
- Document the scope boundary for follow-up exec inspection and daemon-internal healthcheck interpretation.
- Keep lifecycle commit behavior unchanged: no expansion of `SUBMITTABLE_OPERATIONS`, no new lifecycle parent-chain linkage, and no daemon-internal inference layer in this change.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `sock-bridge-lifecycle-classification`: Extend Docktap's canonical request classification contract so Docker exec create/start requests become explicit observation types with stable identifier retention and unchanged lifecycle boundaries.

## Impact

- Affected code: `docktap/proxy/operation_log.py`, `docktap/proxy/docker_proxy.py`, focused Docktap proxy/classifier tests, and Docktap architecture/API docs.
- Affected APIs: Docker Engine API observation for `POST /containers/{id}/exec` and `POST /exec/{id}/start`.
- Affected systems: Docktap runtime observability, healthcheck-style trace readability, and downstream consumers that group read-only exec traffic separately from lifecycle events.