## Context

Sock-bridge currently proxies Docker socket traffic and records operation metadata for measurement. The architecture document now declares a canonical lifecycle sequence and classification model, but implementation has several drift points:

- request ingestion in `handle_client` may stop after header boundary rather than fully consuming body payload bytes
- operation labels are produced by two mapping paths (`get_operation_type` and `_map_path_to_operation`) with inconsistent vocabulary
- some canonical sequence requests (for example preflight and image inspect) are not represented as explicit operation categories
- streaming endpoint detection for versioned Docker API paths can under-classify wait/logs behavior

These gaps reduce trace consistency and can hide lifecycle transitions under `unknown` labels.

## Goals / Non-Goals

**Goals:**

- Guarantee complete request forwarding semantics for HTTP requests with bodies.
- Establish one operation classification source of truth for all emitted operation records/callbacks.
- Align tracked lifecycle visibility with documented canonical sequence, including preflight/image-inspect semantics.
- Ensure streaming behavior decisions reliably match versioned endpoint patterns.
- Add regression tests that fail if classification and forwarding drift reappears.

**Non-Goals:**

- Replacing thread-per-connection model with async/event-loop architecture.
- Introducing persistent operation storage beyond in-memory tracker.
- Redesigning external CLI/API behavior consumed by Docker clients.

## Decisions

1. Single taxonomy contract based on `get_operation_type`
- Decision: all operation labels emitted by proxy logging pathways SHALL derive from `get_operation_type` (directly or via a thin shared adapter).
- Rationale: removes label drift (`run/remove` vs `create/rm`) and keeps docs/tests/runtime consistent.
- Alternative considered: keep callback-specific mapping for legacy compatibility. Rejected because it keeps ambiguity and doubles maintenance.

2. Full request read before forward
- Decision: request ingestion SHALL read headers first, parse `Content-Length` (and handle zero length), then read the full body before `sendall` to Docker.
- Rationale: avoids truncated JSON/body forwarding on fragmented or delayed client sends.
- Alternative considered: preserve current header-boundary behavior and rely on client single-write patterns. Rejected because it is brittle under real network/socket fragmentation.

3. Explicit preflight/inspect visibility policy
- Decision: canonical sequence preflight requests (_ping/info/image inspect) SHALL have deterministic classification policy documented and tested.
- Rationale: prevents key sequence steps being indistinguishable from unrelated background traffic.
- Alternative considered: classify all non-core requests as unknown with no preflight policy. Rejected because it weakens lifecycle observability.

4. Unknown-request passthrough by default
- Decision: requests that do not match identified operation types SHALL be forwarded unchanged (passthrough), while being logged as `unknown` and excluded from parent-chain linkage.
- Rationale: preserves Docker API compatibility for new, less common, or environment-specific endpoints without requiring immediate classifier updates.
- Alternative considered: block unknown operations by default. Rejected because it risks breaking valid Docker client behavior.

5. Version-tolerant streaming endpoint matching
- Decision: streaming detection SHALL be version-agnostic and match endpoint semantics for both versioned and unversioned Docker API paths (for example `/v1.41/containers/<id>/wait` and `/containers/<id>/wait`).
- Rationale: timeout heuristics depend on streaming classification and directly affect stability.
- Alternative considered: keep substring/wildcard mixed matcher as-is. Rejected due to false negatives on real endpoint shapes.

6. Contract tests as change gate
- Decision: add targeted tests for body completeness, mapping consistency, and streaming classification.
- Rationale: these are subtle regressions unlikely to be caught by happy-path lifecycle tests alone.

## Implementation Notes

- Updated request ingestion in `docktap/proxy/docker_proxy.py` to read full request payloads (header + `Content-Length` body) with explicit malformed/incomplete request handling.
- Normalized callback operation typing to canonical `get_operation_type` mapping.
- Added deterministic preflight/image-inspect labels (`preflight_ping`, `preflight_info`, `image_inspect`) in classification logic.
- Updated streaming endpoint detection to be version-agnostic for wait/logs paths.
- Added targeted regression tests in `docktap/tests/test_lifecycle_classification.py`.
- Updated existing mapping expectations in `docktap/tests/test_proxy.py`.
- Stabilized direct Docker pull smoke check in `docktap/test_suite.py` by increasing direct pull socket timeout.

Validation snapshot:
- `pytest -q docktap/tests/test_lifecycle_classification.py` -> 11 passed
- `pytest -q docktap/tests` -> 15 passed (with existing `PytestReturnNotNoneWarning` warnings in legacy tests)
- `python docktap/test_suite.py all` -> 8/8 passed

## Risks / Trade-offs

- [Risk] Broader classification set may require downstream log parser updates if consumers assume current `unknown` values.
  -> Mitigation: document label contract in architecture and provide compatibility notes.

- [Risk] More strict request-reading logic could increase wait time on malformed/incomplete clients.
  -> Mitigation: preserve bounded socket timeouts and emit explicit timeout/error response paths.

- [Risk] Refactoring mapping utilities may affect legacy callback formatting.
  -> Mitigation: keep callback payload shape stable while normalizing only operation value semantics.

- [Risk] Additional tests may require lightweight request-fragment simulation utilities.
  -> Mitigation: add focused helper(s) in test suite rather than broad harness changes.

- [Risk] Passthrough unknown requests may include endpoints that are less visible in operation chains.
  -> Mitigation: keep unknown logging mandatory with method/path/status fields and monitor unknown-rate trends.
