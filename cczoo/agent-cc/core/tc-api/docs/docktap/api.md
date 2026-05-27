# Docktap Python Module and Runtime API Definition

## Scope

This document defines the Docktap Python-side API and the runtime surfaces that the sidecar owns.
It is intended for maintainers, launcher code, integration tests, and adjacent modules that embed or configure Docktap components in-process.

This document does not redefine the runtime engine API itself. Docktap primarily proxies the current Docker-compatible API over a Unix socket and adds trusted-event emission, workload routing, retry bookkeeping, and health reporting around it.

## Module Layout

Recommended Docktap module boundaries:

- `tc_api.docktap.main`: sidecar bootstrap, retention config, health server, process lifecycle.
- `tc_api.docktap.proxy.docker_proxy`: Unix socket proxy server and Docker request forwarding.
- `tc_api.docktap.proxy.runtime_adapter`: runtime-engine normalization boundary and engine identifier helpers.
- `tc_api.docktap.proxy.operation_log`: operation datamodel, parsing helpers, relationship tracking, JSON logging.
- `tc_api.docktap.trucon_client`: TruCon commit client, DSSE construction, retry bookkeeping, workload-chain resolution.
- `tc_api.docktap.workload_store`: persisted `container_id -> workload_id` mapping store.

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
    runtime_engine: str = "docker"
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
DEFAULT_RUNTIME_ENGINE = "docker"
SUPPORTED_RUNTIME_ENGINES = {"docker", "podman"}
```

`WORKLOAD_LABEL` and `LAUNCH_LABEL` define the container-label contract used to route runtime events into workload-scoped chains and correlate them with REST-originated launch attempts.

Canonical v1 runtime-engine identifiers are:

- `docker`
- `podman`

Normalization helpers currently map these aliases onto the canonical identifiers:

- `docker-engine` -> `docker`
- `moby` -> `docker`
- `libpod` -> `podman`

All auditable runtime events SHALL carry `runtime_engine`, even for the current Docker-backed path.

## Runtime Adapter API

`proxy/runtime_adapter.py` owns runtime-engine normalization and the handoff from engine-specific request shapes to Docktap's canonical lifecycle model.

```python
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ParsedRuntimeRequest:
    operation_type: Optional[str]
    path_only: Optional[str]
    params: Dict[str, Any]


class RuntimeAdapter:
    runtime_engine: str

    def parse_request(self, data: bytes) -> ParsedRuntimeRequest:
        ...

    def map_operation(self, path: str, method: str) -> Optional[str]:
        ...

    def parse_operation_metadata(self, request_bytes: bytes, session_id: Optional[str] = None, parent_id: Optional[str] = None):
        ...


class DockerRuntimeAdapter(RuntimeAdapter):
    ...
```

Behavioral requirements:

- Runtime adapters own engine-specific request parsing and normalization.
- Downstream tracking, TruCon commit construction, and verification consume canonical lifecycle metadata rather than engine-specific request shapes.
- Docker remains the v1 default adapter and compatibility target.

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

`get_operation_type(method, path)` maps runtime API calls into Docktap canonical operation classes:

- `/_ping` -> `preflight_ping`
- `/info` -> `preflight_info`
- `GET /images/*/json` -> `image_inspect`
- `GET /networks/*` -> `network_inspect`
- `GET /volumes/*` -> `volume_inspect`
- `GET /plugins/*/json` -> `plugin_inspect`
- `GET /containers/json` -> `container_list`
- `GET /containers/*/logs` -> `container_logs`
- `POST /containers/*/exec` -> `exec_create`
- `POST /exec/*/start` -> `exec_start`
- `/images/create` -> `pull`
- `/containers/create` -> `create`
- `/containers/*/start` -> `start`
- `/containers/*/stop` -> `stop`
- `/containers/*/wait` -> `wait`
- `DELETE /containers/*` -> `rm`
- other `/containers/*` paths -> `inspect`
- `DELETE /images/*` -> `rmi`
- fallback -> `unknown`

Only `pull`, `create`, `start`, `stop`, and `rm` are eligible for TruCon trusted-event submission, regardless of the underlying runtime engine.

`image_inspect`, `network_inspect`, `volume_inspect`, and `plugin_inspect` are read-only observation classes for the primary Docker probe paths in those resource families. They identify which resource family Docker queried during preflight or multi-resource name resolution without changing lifecycle parent-linking or trusted-event submission.

For those four observation classes, Docktap now records a local `response.outcome` field alongside `response.status` with the first-wave values `ok`, `miss`, and `error`. A daemon `404` is treated as a benign `miss` only for those explicit probe classes. Proxy-local failures and other non-benign responses remain `error`.

`container_list` is a read-only observation class for `GET /containers/json` and `GET /v*/containers/json`. It preserves request query parameters in `OperationRecord.params` and does not participate in lifecycle parent-linking or trusted-event submission.

`container_logs` is a read-only observation class for `GET /containers/{id}/logs` and `GET /v*/containers/{id}/logs`. It identifies high-frequency log-read traffic explicitly without changing streaming timeout behavior, lifecycle parent-linking, or trusted-event submission.

`exec_create` and `exec_start` are read-only observation classes for `POST /containers/{id}/exec` and `POST /exec/{id}/start`. They preserve minimal identifier context for `container_id` and `exec_id` without changing lifecycle parent-linking or trusted-event submission. Follow-up exec inspection such as `GET /exec/{id}/json` remains a documented deferred boundary.

Container detail `inspect` remains outside the first-wave benign-miss policy. A `GET /containers/{id}/json` `404` is still recorded without a specialized observation outcome contract until a later change defines that boundary.

The remaining `unknown` bucket is an intentional defer boundary rather than an overflow bin. Current deferred read-only examples include `GET /events`, `GET /containers/{id}/stats`, `GET /containers/{id}/top`, and `GET /exec/{id}/json`; they remain unmapped until a later proposal defines stable observation semantics for them.

## Daemon/Internal Phase Model

The operation types above describe the proxy-observed HTTP API plane only. Mixed traces can also contain daemon/runtime-internal phases that come from Docker daemon or containerd activity rather than from request-path classification.

Docktap's documentation-level daemon/internal taxonomy currently uses five top-level phase families:

- `storage/mount` for layer-store and rootfs preparation activity
- `runtime-spec/bundle` for OCI bundle creation, runtime-spec preparation, and cgroup setup
- `task lifecycle` for containerd task and exec transitions such as create, start, and exit
- `attach/stream` for stdout/stderr attachment and stream completion activity
- `housekeeping` for maintenance work such as exec cleanup after runtime activity finishes

Representative mixed-trace mappings drawn from `openclaw-docker-analysis.md` include:

- `container mounted via layerStore` -> `storage/mount`
- `bundle dir created` and `createSpec: cgroupsPath` -> `runtime-spec/bundle`
- `topic=/tasks/create`, `topic=/tasks/start`, `topic=/tasks/exec-added`, `topic=/tasks/exec-started`, and `topic=/tasks/exit` -> `task lifecycle`
- `attach: stdout: begin`, `attach: stderr: end`, and `attach done` -> `attach/stream`
- `clean 2 unused exec commands` -> `housekeeping`

This second plane is complementary to the API-path observation model. It does not alter `SUBMITTABLE_OPERATIONS`, request parent-linking, or the canonical operation labels produced by `get_operation_type(method, path)`.

The defer boundary is also explicit:

- The taxonomy does not yet define a canonical event schema for daemon/internal phases.
- The taxonomy does not yet define how daemon/internal phases correlate back to API requests or object identifiers.
- Healthcheck-driven exec activity remains a later interpretation problem rather than a top-level phase family.
- Housekeeping anomaly rules and alert-worthy maintenance patterns remain future work.

## Normalized Task-Transition Contract

Inside the daemon/internal `task lifecycle` family, Docktap also defines a documentation-first normalized task-transition contract for mixed Docker traces. This contract adds a stable observation vocabulary for containerd task transitions without changing API-plane operation labels or introducing parser implementation requirements.

The first normalized task-transition set is:

- `tasks/create`
- `tasks/start`
- `tasks/exec-added`
- `tasks/exec-started`
- `tasks/exit`

These normalized observations stay inside the daemon/internal plane and remain distinct from the higher-level HTTP API observations:

- `tasks/create` and `tasks/start` are container-task transitions, not aliases for Docker `create` and `start` requests.
- `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit` are exec-task transitions, not aliases for the API-plane `exec_create` and `exec_start` observations.

The minimum canonical daemon/internal facts for a normalized task transition are:

- `topic`
- `timestamp`
- `source namespace`
- `container identity`
- `exec identity` when reliable exec-specific trace evidence is available

Representative normalized shapes drawn from `openclaw-docker-analysis.md`:

- container-task transition: `topic=/tasks/create` and `topic=/tasks/start` with `namespace=moby` and container-specific trace context
- exec-task transition: `starting exec command <exec-id> in container <container-id>` followed by `topic=/tasks/exec-added`, `topic=/tasks/exec-started`, and `topic=/tasks/exit`

For minimal cold-start interpretation, the required normalized task transitions are `tasks/create` and `tasks/start`. Exec-related transitions remain supplemental for richer runtime interpretation after the primary cold-start path is already understood.

The defer boundary remains explicit:

- This contract does not yet define API-path to daemon/internal correlation rules.
- This contract does not yet decide whether an exec path is healthcheck-driven or foreground workload activity.
- This contract does not yet normalize attach-stream begin/end activity.
- This contract does not yet define a parser or ingestion implementation for daemon/internal events.

## API/Internal Correlation Contract

Docktap also defines a documentation-first correlation contract for joining API-path observations to normalized daemon/internal transitions in mixed Docker traces. The contract is operator-facing: it explains how to read one mixed trace across both planes without redefining API classification or daemon/internal normalization.

The primary correlation shapes are:

- `create` correlations from API-plane container creation to internal preparation and container-task setup
- `start` correlations from API-plane container start to runtime-spec or bundle preparation and `tasks/start`
- exec-path correlations from `exec_create` and `exec_start` to normalized exec-task transitions

The correlation contract uses tiered join evidence:

- strong evidence: full container identity or exec identity shared across the trace
- contextual evidence: timestamp proximity, source namespace, operation shape, and neighboring runtime-preparation steps
- fallback evidence: container name references, short-ID mentions, or nearby preparation context when stronger evidence is missing

Correlation outcomes remain representable even when the trace is imperfect:

- some joins are direct because strong identifiers are available
- some joins remain inferred because only contextual or fallback evidence exists
- some joins remain unresolved because the trace does not expose enough evidence to support a stronger match

Representative correlation shapes drawn from `openclaw-docker-analysis.md`:

- `POST /containers/create` -> internal preparation plus the container-task setup path leading toward `tasks/create`
- `POST /containers/{id}/start` -> runtime-spec or bundle preparation plus `tasks/start`
- `POST /containers/{id}/exec` and `POST /exec/{id}/start` -> `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit`

The defer boundary remains explicit:

- This contract does not define parser or ingestion implementation.
- This contract does not classify exec flows as healthcheck-driven or foreground workload activity.
- This contract does not define attach-stream semantics beyond optional correlation context.
- This contract does not define housekeeping anomaly guidance.

## Secondary Runtime Interpretation Contract

Docktap also defines a documentation-first interpretation contract for secondary runtime activity in mixed Docker traces. This contract sits after normalization and correlation: it explains how to read healthcheck-like exec flows and nearby attach lines without changing API-path classification, normalized exec-task transitions, or correlation evidence tiers.

The first-wave interpretation model is intentionally conservative:

- secondary runtime activity is the top-level reading for daemon-generated or daemon-managed exec flows that are not the primary workload path
- healthcheck-like interpretation is used when the trace has stronger supporting context
- incomplete evidence may remain secondary-runtime or healthcheck-like rather than forcing a binary foreground-versus-healthcheck conclusion

The required runtime spine for a healthy healthcheck-like sequence is:

- `tasks/exec-added`
- `tasks/exec-started`
- `tasks/exit`

Contextual evidence remains separate from that required spine:

- attach begin or end lines for stdout or stderr
- `attach done`
- explicit healthcheck start or completion text in the same local sequence
- repeated cadence that suggests periodic daemon healthcheck execution

Attach lines are stream or transport context around the exec flow:

- they help explain how the daemon attached to and detached from the exec process
- they do not redefine workload lifecycle state
- `attach done` is not itself the workload-completion event

Representative first-wave healthy sequence from `openclaw-docker-analysis.md`:

- `Running health check for container ...`
- `starting exec command ...`
- `tasks/exec-added`
- `tasks/exec-started`
- `tasks/exit`
- `attach: stdout/stderr end`
- `attach done`
- `Health check ... done (exitCode=0)`

Representative first-wave anomalous secondary-runtime shapes:

- repeated failing healthcheck-like exec flows
- `tasks/exec-started` without a corresponding exit in the observed local sequence
- attach begin lines without matching attach completion cues

The defer boundary remains explicit:

- This contract does not define parser or machine confidence implementation.
- This contract does not require binary healthcheck-versus-foreground classification for every exec flow.
- This contract does not define cleanup or maintenance guidance for post-exec activity.
- Housekeeping lines such as exec cleanup remain later GAP-22 work.

## Housekeeping And Internal-Maintenance Interpretation Contract

Docktap also defines a documentation-first interpretation contract for daemon/internal housekeeping activity that appears after primary lifecycle work and secondary runtime activity have already completed. This first-wave contract is intentionally narrow: it explains how operators should read post-runtime maintenance context in mixed traces without redefining runtime paths, parser behavior, or Docktap-local cleanup semantics.

The first-wave housekeeping model keeps three boundaries explicit:

- housekeeping is post-runtime maintenance context rather than a workload lifecycle path
- housekeeping is distinct from secondary runtime exec activity such as healthcheck-like flows
- housekeeping is distinct from Docktap-local retention, retry cleanup, and sidecar sweeper behavior

The first-wave evidence anchor is conservative:

- post-exec cleanup lines such as `clean 2 unused exec commands`
- similarly narrow maintenance residue that appears after nearby exec or runtime activity finishes

Broader maintenance families remain future extension room rather than current contract surface:

- image GC
- background scanning
- retry or reconcile loops

Housekeeping interpretation is contextual-first in this first wave:

- strong container or exec identifiers may be unavailable on housekeeping lines themselves
- local sequence order, timing proximity, and surrounding runtime context may still be sufficient to interpret the line as daemon maintenance
- lack of an object-precise join does not by itself invalidate housekeeping interpretation

Representative first-wave housekeeping shape from `openclaw-docker-analysis.md`:

- healthcheck-like secondary runtime flow completes with `tasks/exec-added`, `tasks/exec-started`, `tasks/exit`, `attach done`, and `Health check ... done (exitCode=0)`
- a later `clean 2 unused exec commands` line is best read as bounded post-runtime housekeeping noise rather than as a new workload transition or continuation of the exec flow

The first-wave signal boundary is intentionally minimal:

- limited delayed cleanup after nearby runtime activity is expected maintenance noise by default
- repeated, unusually dense, or persistently delayed housekeeping that starts to obscure the surrounding runtime story is worth later investigation

The defer boundary remains explicit:

- This contract does not define parser or machine confidence implementation.
- This contract does not define threshold-based alerting or a full anomaly model for maintenance activity.
- This contract does not redefine Docktap-local retention, retry cleanup, or sidecar GC behavior.
- Broader maintenance coverage beyond exec-cleanup-style evidence remains future GAP-22 work.

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
        runtime_engine: str = "docker",
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
- `handle_client()` uses the configured runtime adapter to normalize request parsing and operation metadata before downstream logging and TruCon submission.
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

    def submit_delegation(self, chain_id: str = "default") -> Dict:
        """Create a session delegation event on the specified chain.

        Consumes a valid OIDC token to sign a session.delegation chain event
        via Fulcio, stores the delegation in SQLite, and returns delegation
        metadata including delegation_id and expires_at.
        """
        ...


def has_active_delegation(chain_id: Optional[str] = None) -> bool:
    """Check whether a non-expired delegation exists for the given chain.

    Returns True if the delegations table contains at least one row
    for chain_id (or any chain if None) whose expires_at is in the future.
    """
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

### Session Delegation Behavioral Requirements

- `submit_delegation()` creates a `session.delegation` chain event signed via Fulcio, storing the delegation in the `delegations` table. It returns a dict with `delegation_id`, `expires_at`, and `chain_id`.
- `has_active_delegation()` checks the SQLite `delegations` table for non-expired rows. It is called by the attestation gate and the signing path selector.
- Docktap now defaults to `DOCKTAP_AUTH_MODE=explicit_delegation`, so the proxy gate and `_do_submit()` both require an active delegation before submittable runtime operations are allowed.
- In `explicit_delegation` mode, `_do_submit()` prefers the owner key signing path even if a reusable OIDC token is also present.
- In `delegation_disabled` mode, `_do_submit()` ignores delegation reuse and requires a reusable OIDC token for Fulcio signing.
- When `_do_submit()` finds an active delegation in `explicit_delegation` mode, it switches to the owner key signing path: signs the DSSE envelope with `sign_dsse_with_owner_key()`, constructs an `intoto` v0.0.2 entry via `build_intoto_entry_from_owner_key()`, submits to Rekor via `submit_owner_signed_entry()`, and posts the result to TruCon.
- The delegation-signed predicate includes a `delegation_id` field referencing the active delegation's identifier.
- `delegation_id` is kept on runtime predicates so verification can bind an owner-key-signed business event back to the exact `session.delegation` grant that authorized it. Predecessor continuity is still enforced separately by the chain reservation fields.
- The authorization gate in `docker_proxy.py` is mode-aware: `explicit_delegation` blocks until delegation exists, while `delegation_disabled` blocks until a reusable OIDC token exists.

### Submission Payload Contract

For `SUBMITTABLE_OPERATIONS`, Docktap emits DSSE predicates with the following minimum fields when available:

- `operation_type`
- `operation_result`
- `runtime_engine`
- `workload_id`
- `launch_id`
- `instance_id`
- `image_name`, `image_tag`, `image_digest` for image-oriented operations
- `container_name`, `container_id` for container-oriented operations

This trusted lifecycle `operation_result` field is separate from the local `response.outcome` field used on selected read-only probe observations. `response.outcome` does not widen `SUBMITTABLE_OPERATIONS` and is not part of the TruCon submission contract.

## Session Delegation REST Endpoint

`tc_api.api.app` exposes the readiness and delegation endpoints for Docktap session management.

### `POST /api/docktap/authorize`

Ensures Docktap authorization readiness for the specified chain using service defaults. This is the preferred preflight path for users, wrappers, and future skill integrations.

**Request body:**

```json
{
    "chain_id": "docktap-runtime",
    "identity_token": "<paste token here>"
}
```

- `chain_id` (optional): target chain for the readiness check. For Docktap runtime validation the usual value is `docktap-runtime`.
- `identity_token`: caller-supplied OIDC/Sigstore token used to satisfy readiness or create a delegation when needed.

**Response (200):**

```json
{
    "ready": true,
    "auth_mode": "explicit_delegation",
    "chain_id": "docktap-runtime",
    "scope": ["pull", "create", "start", "stop", "rm"],
    "expires_at": "2025-05-13T18:00:00+00:00",
    "delegation_id": "deleg-xxxxxxxx",
    "source": "created_delegation",
    "detail": null
}
```

**Behavioral notes:**

- In `explicit_delegation` mode, the endpoint reuses an active delegation if it already satisfies the current service policy.
- If no suitable delegation exists and the caller-supplied `identity_token` is valid, the endpoint creates a new delegation using the configured default TTL and scope.
- In `delegation_disabled` mode, the endpoint reports readiness from the caller-supplied `identity_token` instead of creating a delegation.
- Missing or invalid caller tokens are rejected before readiness evaluation begins.
- If readiness cannot be ensured, the endpoint still returns a structured summary with `ready: false` and a machine-readable `source` instead of forcing callers to interpret raw delegation errors.

### `POST /api/docktap/delegate`

Creates a session delegation event that authorizes subsequent Docker operations on the specified chain without requiring per-operation OIDC tokens. This lower-level path is retained for operator/debug workflows; callers should prefer `POST /api/docktap/authorize` for normal preflight behavior.

**Request body:**

```json
{
    "chain_id": "docktap-runtime",
        "identity_token": "<paste token here>",
        "scope": ["pull", "create", "start", "stop", "rm"]
}
```

- `chain_id`: target chain for the delegation. For Docktap runtime validation the usual value is `docktap-runtime`.
- `identity_token`: caller-supplied OIDC/Sigstore token used to sign the delegation event.
- `scope` (optional, default all submittable operations): allowed operation types.

**Response (200):**

```json
{
  "delegation_id": "deleg-xxxxxxxx",
    "chain_id": "docktap-runtime",
  "expires_at": "2025-05-13T18:00:00+00:00"
}
```

**Error responses:**

- `400 Bad Request`: missing caller `identity_token`.
- `401 Unauthorized`: invalid caller OIDC token.
- `500 Internal Server Error`: delegation event creation failed.

**Behavioral notes:**

- The endpoint consumes the caller-supplied OIDC token to sign the delegation event via Fulcio.
- The delegation event is recorded on-chain with `event_type: "session.delegation"`.
- The delegation record is stored in the `delegations` table in `/dev/shm/tc_api_queue/queue.db`.
- Default TTL is 4 hours (14400 seconds), configurable via `DOCKTAP_DELEGATION_TTL_SECONDS`.
- Each delegation is scoped to exactly one chain; delegations on chain A do not authorize operations on chain B.
- The returned `delegation_id` is the stable authorization reference that later owner-key-signed runtime events embed in their predicates so verifiers can prove scope and TTL against the correct grant.

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

This surface proxies the current Docker-compatible engine API traffic. Docktap does not define a new runtime protocol; it intercepts, forwards, normalizes, logs, and post-processes the proxied requests.

### 2. Health Endpoint

Docktap exposes a minimal HTTP health surface:

| Endpoint | Method | Description |
|---|---|---|
| `/healthz` | GET | Return `200 {"status":"ok"}` when the sidecar process is alive. |

This endpoint is intended for process supervision and container orchestration health checks.

## Lifecycle (Python Caller)

```python
from tc_api.docktap.main import SockBridge

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
from tc_api.docktap.proxy.docker_proxy import DockerProxyServer
from tc_api.docktap.trucon_client import TruConCommitter
from tc_api.docktap.workload_store import WorkloadStore

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
- Docktap's internal runtime contract is engine-aware through `runtime_engine`, but its auditable lifecycle model remains canonical across supported engines.
- Docktap does not expose a stable REST control plane beyond `/healthz`.
- `OperationRecord`, `OperationTracker`, `WorkloadStore`, `TruConCommitter`, and `SockBridge` are the main Python-side integration surfaces.
- Workload routing depends on stable interpretation of `io.trucon.workload-id` and `io.trucon.launch-id` labels.
- Only `pull`, `create`, `start`, `stop`, and `rm` are committed to TruCon; other Docker operations may be logged locally but do not become trusted-event submissions.
- Docktap-local retention and retry state are operational helpers only; trusted replay and verification must use TruCon plus immutable backends.
