# Docktap Architecture

This document is the design reference for the docktap sidecar.

## Overview

Docktap is a Unix socket proxy for Docker API traffic that:

- accepts Docker CLI requests through a proxy socket
- forwards requests to the real Docker daemon socket
- captures operation metadata and response status
- tracks operation relationships for pull/create/start/stop/rm flows
- emits structured JSON logs for audit and troubleshooting

Primary runtime entrypoints:

- `stream_test.py`: thin launcher used by test automation
- `main.py`: sidecar bootstrap path that starts `DockerProxyServer`
- `test_suite.py`: single test entrypoint for all integration checks

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
    - parses request metadata
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
- `proxy/operation_log.py`
  - operation model (`OperationRecord`)
  - in-memory operation index (`OperationTracker`)
  - HTTP request/response parsing helpers
  - operation classification (`get_operation_type`)
  - response enrichment and JSON logging
- `stream_test.py`
  - lightweight runtime launcher for the `/tmp/test-stream.sock` path
- `test_suite.py`
  - unified test harness that starts proxy runtime and executes scenarios

## Request Lifecycle

1. Client connects to proxy Unix socket.
2. Proxy reads request bytes until header boundary (`\r\n\r\n`).
3. Metadata is extracted:
   - HTTP method and Docker API path
   - operation type via `get_operation_type`
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
- `stream_test.py` and `main.py` now share behavior through `DockerProxyServer.handle_client`.
