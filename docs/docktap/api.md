# Docktap Python Module and Runtime API Definition

## Scope

This document defines the Docktap Python-side API and the runtime surfaces that the sidecar owns.
It is intended for maintainers, launcher code, integration tests, and adjacent modules that embed or configure Docktap components in-process.

This document does not redefine the Docker Engine API itself. Docktap primarily proxies that API over a Unix socket and adds trusted-event emission, workload routing, retry bookkeeping, and health reporting around it.

## Module Layout

Recommended Docktap module boundaries:

- `docktap.main`: sidecar bootstrap, retention config, health server, process lifecycle.
- `docktap.proxy.docker_proxy`: Unix socket proxy server and Docker request forwarding.
- `docktap.proxy.operation_log`: operation datamodel, parsing helpers, relationship tracking, JSON logging.
- `docktap.trucon_client`: TruCon commit client, DSSE construction, retry bookkeeping, workload-chain resolution.
- `docktap.workload_store`: persisted `container_id -> workload_id` mapping store.

## Core Types

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OperationRecord:
    version: str = "1.0"
    operation_id: str
    parent_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: str = ""
    last_accessed: str = ""
    operation: Dict[str, str] = field(default_factory=dict)
    image: Dict[str, Any] = field(default_factory=dict)
    container: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, str] = field(default_factory=dict)
    response: Dict[str, Any] = field(default_factory=dict)
    user: Dict[str, str] = field(default_factory=dict)


@dataclass
class PendingSubmission:
    operation_type: str
    bundle_json: str
    chain_id: str
    event_digest: str
    event_id: str
    idempotency_key: str
    instance_id: Optional[str]
    status: str = "retryable"
    retry_attempts: int = 0
    next_attempt_at: float = 0.0
    last_error: Optional[str] = None
    record_id: Optional[str] = None
    sequence_num: Optional[int] = None
    resolved_at: Optional[float] = None


@dataclass
class DocktapRetentionConfig:
    gc_interval_seconds: float = 300.0
    operation_retention_hours: float = 24.0
    removed_container_retention_hours: float = 24.0
    acknowledged_retry_retention_hours: float = 24.0
    terminal_retry_retention_hours: float = 168.0
```

## Constants and Labels

```python
WORKLOAD_LABEL = "io.trucon.workload-id"
LAUNCH_LABEL = "io.trucon.launch-id"

SUBMITTABLE_OPERATIONS = {"pull", "create", "start", "stop", "rm"}
```

`WORKLOAD_LABEL` and `LAUNCH_LABEL` define the container-label contract used to route runtime events into workload-scoped chains and correlate them with REST-originated launch attempts.

## Operation Log API

`proxy/operation_log.py` owns the internal operation datamodel, parsing helpers, and relationship tracker.

```python
from typing import Any, Dict, List, Optional, Tuple


class OperationTracker:
    def __init__(self) -> None:
        ...

    def add(self, op: OperationRecord) -> None:
        ...

    def touch(self, operation_id: str) -> None:
        ...

    def get_by_container_name(self, container_name: str) -> Optional[OperationRecord]:
        ...

    def get_by_container_id(self, container_id: str) -> Optional[OperationRecord]:
        ...

    def get_by_container(self, container_id: str) -> List[OperationRecord]:
        ...

    def get_by_image(self, image_digest: str) -> List[OperationRecord]:
        ...

    def get_by_session(self, session_id: str) -> List[OperationRecord]:
        ...

    def get_all_operations(self) -> List[OperationRecord]:
        ...

    def get_operation_by_id(self, operation_id: str) -> Optional[OperationRecord]:
        ...

    def find_pull_for_image(self, image_name: str) -> Optional[OperationRecord]:
        ...

    def find_create_for_container(self, container_name: str) -> Optional[OperationRecord]:
        ...

    def cleanup_old_operations(self, max_age_hours: int = 24) -> int:
        ...

    def get_operation_chain(self, operation_id: str) -> List[OperationRecord]:
        ...


def parse_http_request(request_bytes: bytes) -> Tuple[str, str, Dict[str, str], bytes]:
    ...


def parse_http_response(response_bytes: bytes) -> Tuple[int, Dict[str, str], bytes]:
    ...


def parse_query_params(path: str) -> Dict[str, str]:
    ...


def parse_json_body(body: bytes) -> Dict[str, Any]:
    ...


def extract_container_id(path: str) -> Optional[str]:
    ...


def extract_digest_from_pull_response(body: bytes) -> Optional[str]:
    ...


def is_streaming_endpoint(path: str) -> bool:
    ...


def get_operation_type(method: str, path: str) -> str:
    ...


def parse_operation_metadata(
    request_bytes: bytes,
    session_id: Optional[str] = None,
    parent_id: Optional[str] = None,
) -> OperationRecord:
    ...
```

### OperationTracker Behavioral Requirements

- `OperationTracker` is thread-safe; all reads and writes are guarded by an internal lock.
- `add()` updates both the primary operation map and auxiliary indexes for image digest, container ID, and container name.
- `find_pull_for_image()` returns the most recent matching `pull` operation by normalized image name.
- `find_create_for_container()` resolves create operations by exact container name, full container ID, or short-ID prefix match.
- `cleanup_old_operations()` removes stale in-memory state only; it is a retention helper, not an audit source of truth.

### Operation Classification Contract

`get_operation_type(method, path)` maps Docker Engine API calls into Docktap operation classes:

- `/_ping` -> `preflight_ping`
- `/info` -> `preflight_info`
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

Only `pull`, `create`, `start`, `stop`, and `rm` are eligible for TruCon trusted-event submission.

## Docker Proxy API

`proxy/docker_proxy.py` owns the Docker Unix-socket interception path.

```python
from typing import Any, Dict, Optional, Tuple


class DockerProxyServer:
    def __init__(
        self,
        listen_socket_path: str = "/tmp/docker-proxy.sock",
        docker_socket_path: str = "/var/run/docker.sock",
        trucon_committer = None,
    ) -> None:
        ...

    def set_log_callback(self, callback) -> None:
        ...

    def forward_to_docker(self, request_data: bytes, request_path: str = "") -> Optional[bytes]:
        ...

    def handle_client(self, client_socket) -> None:
        ...

    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    @staticmethod
    def _extract_workload_id(request_data: bytes) -> Optional[str]:
        ...

    @staticmethod
    def _extract_launch_id(request_data: bytes) -> Optional[str]:
        ...
```

### DockerProxyServer Behavioral Requirements

- `start()` binds the proxy socket, listens, and processes each accepted client in a dedicated thread.
- `handle_client()` must forward the original Docker API request to the real daemon socket and return the response to the caller before any best-effort TruCon submission can block the client.
- `handle_client()` records operation metadata, parent-child linkage, response enrichment, and JSON logging for every handled request.
- If `trucon_committer` is configured, `handle_client()` submits trusted events only for `SUBMITTABLE_OPERATIONS`.
- `create` requests may carry workload and launch routing hints through `WORKLOAD_LABEL` and `LAUNCH_LABEL` embedded in the Docker create request body.
- Docktap does not alter Docker Engine API semantics beyond proxying, logging, and post-response trusted-event submission.

## Workload Store API

`workload_store.py` persists runtime routing state across Docktap process restarts.

```python
from typing import Any, Dict, Optional


class WorkloadStore:
    def __init__(self, db_path: str = "/dev/shm/docktap/container_map.db") -> None:
        ...

    def init_db(self) -> None:
        ...

    def put(
        self,
        container_id: str,
        workload_id: str,
        launch_id: Optional[str] = None,
        operation: str = "create",
    ) -> None:
        ...

    def touch(self, container_id: str, operation: str) -> None:
        ...

    def get(self, container_id: str) -> Optional[str]:
        ...

    def get_metadata(self, container_id: str) -> Optional[Dict[str, Any]]:
        ...

    def cleanup_removed(self, max_age_hours: float = 24) -> int:
        ...
```

### WorkloadStore Behavioral Requirements

- `init_db()` is safe to call at every startup and preserves existing mapping rows.
- `put()` upserts `container_id -> workload_id` and preserves an existing `launch_id` when a later update omits one.
- `touch()` refreshes lifecycle timestamps and terminal `rm` metadata without changing workload identity.
- `cleanup_removed()` deletes only mappings whose `removed_at` grace window has expired.
- `WorkloadStore` is an operational routing cache, not a source of verifiable chain history; authoritative replay remains in TruCon and immutable backends.

## TruCon Commit Client API

`trucon_client.py` owns DSSE construction and trusted runtime-event submission.

```python
from typing import Dict, List, Optional


class RetryQueuedError(RuntimeError):
    ...


class TruConCommitter:
    def __init__(
        self,
        trucon_url: Optional[str] = None,
        workload_store = None,
        *,
        max_retry_attempts: Optional[int] = None,
        retry_base_delay: Optional[float] = None,
        retry_max_delay: Optional[float] = None,
        retry_poll_interval: float = 0.25,
        acknowledged_retention_hours: Optional[float] = None,
        terminal_retention_hours: Optional[float] = None,
        start_retry_worker: bool = True,
    ) -> None:
        ...

    def submit_operation(
        self,
        op_record,
        operation_type: str,
        *,
        workload_id: Optional[str] = None,
        launch_id: Optional[str] = None,
    ) -> bool:
        ...

    def shutdown(self) -> None:
        ...

    def process_retry_queue(self, now: Optional[float] = None) -> None:
        ...

    def get_retry_snapshot(self) -> List[Dict[str, Optional[str]]]:
        ...

    def cleanup_resolved_submissions(self, now: Optional[float] = None) -> int:
        ...
```

### TruConCommitter Behavioral Requirements

- `submit_operation()` never raises to the Docker proxy caller; it returns `True` on immediate success and `False` on failure or retry queuing.
- Docktap constructs and signs DSSE bundles locally using ambient OIDC credentials, then POSTs them to TruCon `/commit` through the shared internal transport helper.
- `pull` always routes to the `default` chain.
- `create` routes to `workload_id` when the `io.trucon.workload-id` label is present; otherwise it falls back to `default`.
- `start`, `stop`, and `rm` resolve `chain_id` from `WorkloadStore` based on `container_id`.
- `instance_id` is the Docker `container_id` for container lifecycle operations and `None` for `pull`.
- Initial retryable TruCon failures may be queued for asynchronous retry after the Docker response has already been returned.
- Retry bookkeeping is local and bounded; authoritative commit confirmation remains TruCon's responsibility.

### Submission Payload Contract

For `SUBMITTABLE_OPERATIONS`, Docktap emits DSSE predicates with the following minimum fields when available:

- `operation_type`
- `operation_result`
- `workload_id`
- `launch_id`
- `instance_id`
- `image_name`, `image_tag`, `image_digest` for image-oriented operations
- `container_name`, `container_id` for container-oriented operations

## Sidecar Bootstrap API

`main.py` provides the process-level sidecar launcher.

```python
from dataclasses import dataclass


@dataclass
class DocktapRetentionConfig:
    gc_interval_seconds: float = 300.0
    operation_retention_hours: float = 24.0
    removed_container_retention_hours: float = 24.0
    acknowledged_retry_retention_hours: float = 24.0
    terminal_retry_retention_hours: float = 168.0

    @classmethod
    def from_env(cls) -> "DocktapRetentionConfig":
        ...


class SockBridge:
    def __init__(self, socket_path: str, docker_socket_path: str) -> None:
        ...

    def log_callback(self, event_data: dict) -> None:
        ...

    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...


def start_health_server(port: int = 8002) -> None:
    ...


def parse_args():
    ...


def main() -> None:
    ...
```

### SockBridge Behavioral Requirements

- `SockBridge` initializes `WorkloadStore`, `TruConCommitter`, `DockerProxyServer`, the health server, and the local-state sweeper.
- `start()` is the canonical production/bootstrap entrypoint for the Docktap sidecar.
- `stop()` shuts down the sweeper, proxy server, and TruCon retry worker in that order.
- Retention windows for operation tracker state, removed container mappings, and resolved retry submissions are loaded from environment variables through `DocktapRetentionConfig.from_env()`.

## Runtime Surfaces

Docktap owns the following runtime-facing surfaces:

### 1. Docker Unix Socket Proxy

Docktap listens on a configured Unix socket path such as `/tmp/docker-proxy.sock` or `/var/run/docktap/docker.sock`.

Clients use it by setting:

```bash
export DOCKER_HOST=unix:///var/run/docktap/docker.sock
```

This surface proxies Docker Engine API traffic. Docktap does not define a new Docker protocol; it intercepts, forwards, logs, and post-processes the proxied requests.

### 2. Health Endpoint

Docktap exposes a minimal HTTP health surface:

| Endpoint | Method | Description |
|---|---|---|
| `/healthz` | GET | Return `200 {"status":"ok"}` when the sidecar process is alive. |

This endpoint is intended for process supervision and container orchestration health checks.

## Lifecycle (Python Caller)

```python
from docktap.main import SockBridge

app = SockBridge(
    socket_path="/tmp/docker-proxy.sock",
    docker_socket_path="/var/run/docker.sock",
)

app.start()

# In another process or shell:
# export DOCKER_HOST=unix:///tmp/docker-proxy.sock
# docker pull nginx:alpine
# docker create --label io.trucon.workload-id=my-app nginx:alpine
# docker start <container>

# On shutdown:
app.stop()
```

For lower-level test or embedding scenarios:

```python
from docktap.proxy.docker_proxy import DockerProxyServer
from docktap.trucon_client import TruConCommitter
from docktap.workload_store import WorkloadStore

store = WorkloadStore(db_path="/tmp/map.db")
store.init_db()
committer = TruConCommitter(workload_store=store, start_retry_worker=False)
proxy = DockerProxyServer(
    listen_socket_path="/tmp/docker-proxy.sock",
    docker_socket_path="/var/run/docker.sock",
    trucon_committer=committer,
)

proxy.start()
```

## Error Model

Docktap intentionally keeps its public error surface small:

```python
class RetryQueuedError(RuntimeError):
    """Raised internally after an initial retryable TruCon failure is queued."""
```

Behavioral expectations:

- `RetryQueuedError` is an internal control-flow signal, not a caller-facing runtime contract.
- Docker proxy callers should receive Docker responses whenever possible, even when TruCon submission later fails or is queued for retry.
- Proxy transport failures to the real Docker daemon surface to the Docker client as HTTP `400` or `503` responses generated by Docktap.

## Compatibility Rules

- Docktap's primary external compatibility target is the Docker Engine API over a Unix socket proxy.
- Docktap does not expose a stable REST control plane beyond `/healthz`.
- `OperationRecord`, `OperationTracker`, `WorkloadStore`, `TruConCommitter`, and `SockBridge` are the main Python-side integration surfaces.
- Workload routing depends on stable interpretation of `io.trucon.workload-id` and `io.trucon.launch-id` labels.
- Only `pull`, `create`, `start`, `stop`, and `rm` are committed to TruCon; other Docker operations may be logged locally but do not become trusted-event submissions.
- Docktap-local retention and retry state are operational helpers only; trusted replay and verification must use TruCon plus immutable backends.
