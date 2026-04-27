# Docktap Architecture

This document is the design reference for the docktap sidecar.

## Overview

Docktap is a Unix socket proxy for container-runtime API traffic that:

- accepts Docker CLI requests through a proxy socket
- forwards requests to the real Docker daemon socket
- captures operation metadata and response status
- normalizes engine-specific request handling through a runtime adapter boundary
- tracks operation relationships for pull/create/start/stop/rm flows
- submits signed DSSE bundles to TruCon for trusted event recording
- emits the runtime identity, runtime engine, and outcome fields required by the `docktap-runtime` verification profile
- propagates `launch_id` for runtime events that belong to a REST-originated launch flow
- maintains bounded local routing, mapping, and retry state via periodic garbage collection
- emits structured JSON logs for audit and troubleshooting
- exposes an HTTP health endpoint (`/healthz`) for container orchestration

Primary runtime entrypoints:

- `stream_test.py`: thin launcher used by test automation
- `main.py`: sidecar bootstrap path that starts `DockerProxyServer` and health server
- `test_suite.py`: single test entrypoint for all integration checks

## Deployment

Docktap is deployed as an independent service alongside tc_api and TruCon:

- **Docker Compose**: Independent container using the same image as tc_api, with Docker daemon socket bind-mount and proxy socket exposed via `/var/run/docktap/`.
- **Bare-metal** (`start.sh`): Background process launched after TruCon, with PID tracking and graceful shutdown.

Current internal TruCon communication prefers the shared Unix domain socket transport used across the same-machine deployment. TruCon derives Docktap caller identity from peer credentials and applies a commit-oriented admission policy; internal HTTP plus a shared Bearer token remains only as a compatibility path.

Users route Docker CLI through the proxy by setting `DOCKER_HOST=unix:///var/run/docktap/docker.sock`.

The v1 runtime adapter contract uses canonical engine identifiers:

- `docker`
- `podman`

Normalization rules for future onboarding:

- `docker-engine` and `moby` normalize to `docker`
- `libpod` normalizes to `podman`

Docktap failure model: if Docktap goes down, Docker CLI traffic is blocked (by design — all operations must be recorded). Automatic restart ensures minimal downtime.

## High-Level Architecture

```text
Docker CLI (DOCKER_HOST=unix:///tmp/test-stream.sock)
            |
            v
  stream_test.py (launcher)
            |
            v
  DockerProxyServer.handle_client
    - accepts client socket
    - delegates request normalization to runtime adapter
    - links operation parent_id
    - forwards to /var/run/docker.sock
    - enriches operation with response
    - writes JSON log event
            |
            v
      Docker Daemon Socket
```

## Component Layout

- `proxy/docker_proxy.py`
  - reusable Unix socket proxy server abstraction used by `main.py`
  - thread-per-connection concurrency in `start()`
  - full request lifecycle in `handle_client()`
- `proxy/runtime_adapter.py`
  - runtime-engine normalization boundary
  - canonical engine identifiers and alias normalization
  - adapter-backed request parsing and metadata construction
- `proxy/operation_log.py`
  - operation model (`OperationRecord`)
  - in-memory operation index (`OperationTracker`)
  - HTTP request/response parsing helpers
  - operation classification (`get_operation_type`)
  - response enrichment and JSON logging
- `workload_store.py`
  - persisted container-to-workload and launch-boundary mappings on tmpfs
  - lifecycle metadata for `created_at`, `last_seen_at`, `removed_at`, and `last_operation`
- `trucon_client.py`
  - TruCon commit client, runtime audit-field construction, and bounded retry bookkeeping
  - uses the shared TruCon internal transport helper with UDS-first behavior and caller-identity-aware admission policy
  - local retry retention for pending, acknowledged, and terminal outcomes
- `stream_test.py`
  - lightweight runtime launcher for the `/tmp/test-stream.sock` path
- `test_suite.py`
  - unified test harness that starts proxy runtime and executes scenarios

## Request Lifecycle

1. Client connects to proxy Unix socket.
2. Proxy reads request bytes until header boundary (`\r\n\r\n`).
3. Metadata is extracted:
  - runtime engine via the configured runtime adapter
  - HTTP method and runtime API path
  - canonical operation type via `get_operation_type`
   - image/container hints from query/body/path
4. Parent operation is resolved from tracker:
   - `create` links to most recent matching `pull`
   - `start`/`stop`/`rm` link to matching `create`
5. Request is forwarded to Docker socket.
6. Response bytes are read and returned to the caller.
7. Operation is enriched with response fields:
   - HTTP status
   - pull digest (if present)
   - create container ID (if present)
   - wait status code (if present)
8. Final operation record is added to tracker and logged as JSON.
9. For auditable lifecycle operations, Docktap emits a TruCon commit containing operation outcome, workload/instance/image identity, and `launch_id` when the event belongs to an active REST launch flow.
10. Each auditable runtime event carries explicit `runtime_engine` metadata so the verifier can run one mixed-engine runtime profile while dispatching engine-specific checks internally.

## Concurrency Model

Current runtime (`DockerProxyServer`) uses thread-per-connection handling:

- each accepted client connection is processed in a dedicated thread
- tracker mutations/reads are guarded by a lock in `OperationTracker`
- shared indexes are updated atomically under lock:
  - operation map by ID
  - image digest map
  - container name map
  - container ID map

This approach favors low implementation complexity and is adequate for I/O-heavy Docker socket traffic.

## Data Model

Core structure in `proxy/operation_log.py`:

- `OperationRecord`
  - identity: `operation_id`, `parent_id`, `session_id`
  - timing: `timestamp`, `last_accessed`
  - operation descriptor: type/action/api path/method
  - resource metadata: image and container fields
  - request params and response status fields

- `OperationTracker`
  - add/get/query primitives
  - matching helpers:
    - `find_pull_for_image`
    - `find_create_for_container`
  - retention helper:
    - `cleanup_old_operations(max_age_hours=24)`

- `WorkloadStore`
  - persisted mapping state for `container_id -> workload_id` and optional `launch_id`
  - lifecycle metadata:
    - `created_at`
    - `last_seen_at`
    - `removed_at`
    - `last_operation`
  - removed-container cleanup after an rm grace window

## Trusted Event Contract

For the lifecycle operations that Docktap submits to TruCon (`pull`, `create`, `start`, `stop`, `rm`), the emitted DSSE predicate now carries the minimum fields required for runtime verification:

- `operation_type`
- `operation_result`
- `runtime_engine`
- `workload_id` for workload-scoped operations
- `instance_id` for container-scoped operations
- `image_digest` or equivalent stable image identity when the operation meaning depends on an image target
- `launch_id` when the runtime event is attributable to a REST-originated launch flow

This contract lets `tc-verify` distinguish successful versus failed runtime actions, keep one `docktap-runtime` profile across engines, and correlate REST launch intent with observed container creation/start evidence.

## Docker Operation Mapping & Lifecycle

This section documents the canonical request sequence observed in normal Docker flows
and maps endpoint patterns to the operation types produced by
`proxy/operation_log.py:get_operation_type`.

### Canonical Request Sequence (Typical Run)

1. Client preflight and capability checks:
  - `GET /_ping`
  - `GET /v*/info`
2. Image preflight checks:
  - `GET /v*/images/<image>/json`
  - a `404` here is expected when image is not local yet
3. Pull missing image:
  - `POST /v*/images/create?fromImage=<image>&tag=<tag>`
4. Create container from image:
  - `POST /v*/containers/create?name=<container>`
5. Start container:
  - `POST /v*/containers/<id>/start`
6. Observe and manage runtime:
  - common inspect/list/status calls such as `GET /v*/containers/<id>/json`
  - optional wait/logs calls such as `POST /v*/containers/<id>/wait`
7. Stop and remove lifecycle:
  - `POST /v*/containers/<id>/stop`
  - `DELETE /v*/containers/<id>`

Notes:

- Pre-pull image inspect `404` responses are not failures in this flow. They are
  normal cache-miss checks before a pull.
- Extra inspect/list requests may appear between core lifecycle calls depending on
  Docker client version and command options.

### Endpoint-to-Operation Mapping

`get_operation_type(method, path)` classifies Docker API calls as:

- `GET /_ping` -> `preflight_ping`
- `GET /info` -> `preflight_info`
- `GET /images/*/json` -> `image_inspect`
- `/images/create` -> `pull`
- `/containers/create` -> `create`
- `/containers/*/start` -> `start`
- `/containers/*/stop` -> `stop`
- `/containers/*/wait` -> `wait`
- `DELETE /containers/*` -> `rm`
- other `/containers/*` paths -> `inspect`
- `DELETE /images/*` -> `rmi`
- fallback -> `unknown`

### Parent Linking Expectations

Relationship linking in the tracker follows these rules:

- `create` links to the most recent matching `pull` for the image.
- `start`, `stop`, and `rm` link to the matching `create` for the container.
- `inspect` and `unknown` operations are recorded but typically do not become chain
  parents in the core pull/create/start/stop/rm lifecycle.

## Logging Contract

The proxy emits JSON events with stable keys suitable for downstream audit processing:

- `version`
- `operation_id`
- `parent_id`
- `session_id`
- `timestamp`
- `runtime_engine`
- `operation`
- `image`
- `container`
- `params`
- `response`
- `user`

## Runtime Configuration

Common socket defaults:

- proxy socket: `/tmp/test-stream.sock` (runtime/test path)
- Docker daemon socket: `/var/run/docker.sock`

`main.py` also supports configurable values through CLI flags and env vars:

- `--socket-path` / `SOCK_BRIDGE_SOCKET`
- `--docker-socket-path` / `DOCKER_SOCKET`
- `DOCKTAP_GC_INTERVAL_SECONDS`
- `DOCKTAP_OPERATION_RETENTION_HOURS`
- `DOCKTAP_REMOVED_CONTAINER_RETENTION_HOURS`
- `DOCKTAP_ACKED_RETRY_RETENTION_HOURS`
- `DOCKTAP_TERMINAL_RETRY_RETENTION_HOURS`

## Test Strategy

Use one entrypoint:

```bash
cd docktap
python test_suite.py all
```

Representative modes:

- `lifecycle`
- `parallel-images`
- `multi-container`
- `mixed`
- `session`

## Operational Notes

- For test automation and current proxy behavior validation, use `stream_test.py` indirectly via `test_suite.py`.
- Keep tracker and parsing logic in `proxy/operation_log.py` to avoid duplicate behavior across runtimes.
- Keep engine-specific request normalization in `proxy/runtime_adapter.py` so TruCon commit logic and verifier-facing event semantics remain canonical.
- `stream_test.py` and `main.py` now share behavior through `DockerProxyServer.handle_client`.
- Docktap local state is operational cache and short-lived diagnostics only. Replay correctness comes from TruCon and immutable backends, not from Docktap-local retention.
- A background sweeper periodically removes expired operation records, removed-container mappings, and resolved retry records while preserving retryable items until they are acknowledged or terminally exhausted.
