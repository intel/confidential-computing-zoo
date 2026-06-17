## Why

Docktap documentation now defines a canonical Docker request lifecycle, but the runtime implementation does not fully satisfy that contract in critical areas (request-body completeness, operation-label consistency, and streaming endpoint handling). This creates observability drift and intermittent correctness risks under real Docker traffic patterns.

## What Changes

- Normalize request handling in `DockerProxyServer.handle_client` so proxied requests include complete request bodies, not only headers.
- Unify operation classification to a single source of truth (`get_operation_type`) for all emitted operation logs.
- Expand lifecycle-aware operation visibility for canonical preflight and image-inspect traffic so key sequence steps are not collapsed into ambiguous categories.
- Harden streaming endpoint detection for versioned Docker API paths (for example wait/logs) to avoid premature timeout behavior.
- Add targeted tests for fragmented request body forwarding, operation-label consistency, and streaming response handling.

## Capabilities

### New Capabilities
- `sock-bridge-lifecycle-classification`: Ensure lifecycle-aligned operation classification and complete request forwarding semantics for docktap proxy traffic.

### Modified Capabilities
- None.

## Impact

- Affected code:
  - `docktap/proxy/docker_proxy.py`
  - `docktap/proxy/operation_log.py`
  - `docktap/test_suite.py` and/or `docktap/tests/*`
  - `docktap/architecture.md` (minor alignment updates if wording changes)
- Runtime behavior:
  - More accurate operation chain linkage and telemetry consistency.
  - Improved robustness for larger/fragmented request payloads.
- Testing:
  - New/updated tests to prevent regressions in lifecycle mapping and streaming behavior.
