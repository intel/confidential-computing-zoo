# Docktap Architecture

This document is the design reference for the docktap sidecar.

Concrete operator commands for local startup, smoke validation, and test execution are intentionally documented in `docs/TESTING.md` and the top-level `README.md`. This document keeps the Docktap runtime model, contracts, and internal boundaries.

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


### Docktap Authorization

Docktap uses the same OIDC / Sigstore identity model as the rest of the control plane, but runtime authorization is now delegation-first by default.

Current operator contract:

- `./start.sh restart` starts `tc_api`, TruCon, and Docktap together.
- `DOCKTAP_REQUIRE_ATTESTATION=1` is enabled by default.
- `DOCKTAP_AUTH_MODE=explicit_delegation` is the default.
- In `explicit_delegation` mode, submittable Docker operations such as `pull` are blocked until the user completes OIDC login and passes Docktap authorization readiness for the target chain. The readiness path reuses a valid delegation when possible and creates one with service defaults when needed.
- `DOCKTAP_AUTH_MODE=delegation_disabled` is the stricter override for environments that want per-operation OIDC-backed authorization instead of delegation reuse.
- The older local lifecycle grant shortcut for follow-up `start`/`stop`/`rm` operations has been removed. Runtime reuse now happens only through an explicit delegation record.

Recommended flows:

- Same-machine browser access: complete browser login, capture the returned `identity_token`, call `POST /api/docktap/authorize` with that token, then retry the Docker command.
- Remote SSH with browser reachability: set `DOCKTAP_ATTESTATION_BROWSER_BASE_URL` before startup.
- Remote SSH without callback reachability: use the out-of-band `tc-client` login command from the challenge, then call `POST /api/docktap/authorize` with the emitted `identity_token`.
- Non-interactive launchers: pre-acquire a token and call `POST /api/docktap/authorize` up front with that `identity_token`, or set `DOCKTAP_AUTH_MODE=delegation_disabled` if delegation reuse is intentionally forbidden.

Example OOB flow:

```shell
./start.sh restart
tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
curl -X POST http://127.0.0.1:8000/api/docktap/authorize \
	-H 'Content-Type: application/json' \
	-d '{"chain_id": "default", "identity_token": "<paste token here>"}'
docker exec -e DOCKER_HOST=unix:///var/run/docktap/docker.sock openclaw-gateway sh -lc 'docker pull hello-world:latest'
```

Example challenge error:

```text
Error response from daemon: Docktap authorization required before docker pull.
Browser login: http://127.0.0.1:8000/api/sigstore/interactive-login?operation=docktap&session_id=<session-id>
Remote login command: tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
Ensure authorization: curl -X POST http://127.0.0.1:8000/api/docktap/authorize -H 'Content-Type: application/json' -d '{"chain_id": "default", "identity_token": "<paste token here>"}'
Direct delegation fallback: curl -X POST http://127.0.0.1:8000/api/docktap/delegate -H 'Content-Type: application/json' -d '{"chain_id": "default", "identity_token": "<paste token here>"}'
If tc-client is unavailable, from the tc_api repo root run: bash setup.sh
Then run: ./venv/bin/tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
Then retry.
```

`delegation_id` is intentionally kept in runtime predicates. Chain continuity is still enforced by the reserved predecessor fields (`prev_event_digest` and `prev_lookup_hash`), but `delegation_id` separately binds an owner-key-signed runtime event back to the specific `session.delegation` grant that authorized it. Verification uses that reference to prove scope and TTL, which predecessor linkage alone cannot express.

### Docktap Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TRUCON_URL` | `http://127.0.0.1:8001` | TruCon endpoint for event submission |
| `TRUCON_UDS_PATH` | `/var/run/trucon/trucon.sock` | Preferred same-machine Unix socket path for tc_api and Docktap internal TruCon traffic |
| `TRUCON_SERVICE_TOKEN` | (generated) | Shared Bearer token for TruCon auth |
| `SOCK_BRIDGE_SOCKET` | `/tmp/docker-proxy.sock` | Proxy socket listen path |
| `DOCKER_SOCKET` | `/var/run/docker.sock` | Docker daemon socket path |
| `DOCKTAP_HEALTH_PORT` | `8002` | HTTP health endpoint port |
| `DOCKTAP_SOCKET` | `/var/run/docktap/docker.sock` | Proxy socket path (bare-metal `start.sh`) |
| `DOCKTAP_REQUIRE_ATTESTATION` | `1` | Keep the Docktap authorization gate enabled for submittable runtime operations |
| `DOCKTAP_AUTH_MODE` | `explicit_delegation` | Runtime authorization mode: explicit delegation by default, or `delegation_disabled` for stricter per-operation OIDC-only behavior |
| `DOCKTAP_DELEGATION_TTL_SECONDS` | `14400` | Default delegation lifetime in seconds for `POST /api/docktap/delegate` |
| `DOCKTAP_ATTESTATION_API_URL` | `http://127.0.0.1:8000` | Base API URL embedded in the attestation-login challenge |
| `DOCKTAP_ATTESTATION_BROWSER_BASE_URL` | `http://127.0.0.1:8000` | Browser-visible base URL embedded in the attestation-login challenge |
| `DOCKTAP_LOG_FILE` | `./logs/docktap-latest.log` | Docktap runtime log path used by `start.sh` |
| `TRUCON_LOG_FILE` | `./logs/trucon-latest.log` | TruCon runtime log path used by `start.sh` |


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

## Session Delegation

Session delegation solves the short-lived OIDC token problem for Docktap runtime operations. Instead of requiring a fresh OIDC token per Docker operation, the user authenticates once, runs authorization readiness, and reuses the resulting explicit grant for later runtime operations on the same chain until TTL or scope runs out.

Docktap now defaults to `DOCKTAP_AUTH_MODE=explicit_delegation`.

- In `explicit_delegation` mode, the proxy gate requires an active delegation before allowing submittable runtime operations.
- `DOCKTAP_AUTH_MODE=delegation_disabled` is the stricter override for environments that want OIDC-backed authorization on each runtime operation and do not want delegation reuse.
- The older in-memory lifecycle grant for nearby `start`/`stop`/`rm` operations is gone. Reuse now comes only from an explicit delegation record.

### Authorization Readiness Flow

1. User, wrapper, or agent calls `POST /api/docktap/authorize` with an optional `chain_id` and an explicit caller `identity_token`.
2. tc_api reuses an active delegation if it already satisfies the current service policy.
3. If no suitable delegation exists and the caller-supplied OIDC token is valid, tc_api creates a `session.delegation` chain event signed via Fulcio.
4. The delegation record is stored in the existing SQLite database at `/dev/shm/tc_api_queue/queue.db`.
5. The readiness response returns whether authorization is ready, the effective scope, and delegation expiry when applicable.
6. Subsequent Docker operations on the authorized chain use the owner key signing path instead of Fulcio when explicit delegation is active.

`POST /api/docktap/delegate` remains available as a lower-level operator/debug endpoint when direct delegation creation is needed, and it also requires an explicit caller `identity_token`.

### Signing Path Selection

When Docktap submits a trusted event, the signing path is selected as follows:

1. **`explicit_delegation` + active delegation** → Owner key signing:
   - The DSSE envelope is signed with the chain owner key (ECDSA P-384 + SHA-256).
   - An `intoto` v0.0.2 proposed entry is constructed with the raw owner public key PEM.
   - The entry is submitted to Rekor via `POST /api/v1/log/entries`.
   - The predicate includes `delegation_id` referencing the active delegation.
2. **`explicit_delegation` + no active delegation + `DOCKTAP_REQUIRE_ATTESTATION=1`** → HTTP 428 authorization gate with OIDC-login and readiness-preflight instructions, plus raw delegation fallback.
3. **`delegation_disabled` + reusable OIDC token** → Fulcio signing.
4. **`delegation_disabled` + no reusable OIDC token + `DOCKTAP_REQUIRE_ATTESTATION=1`** → HTTP 428 attestation-login gate.

`delegation_id` is not a replacement for the chain predecessor contract. Chain order and continuity still come from TruCon's reserved `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`. `delegation_id` exists in parallel so verifiers can bind an owner-key-signed runtime event back to the exact `session.delegation` event that authorized it and then evaluate TTL and scope on that grant.

### Delegation Storage

Delegations are stored in the `delegations` table alongside the existing `commit_queue` and `chain_state` tables:

| Column | Type | Description |
|---|---|---|
| `delegation_id` | TEXT PK | Unique delegation identifier |
| `chain_id` | TEXT | Target chain |
| `scope` | TEXT (JSON) | Allowed operation types |
| `expires_at` | TEXT | ISO 8601 expiry timestamp |
| `created_at` | TEXT | Creation timestamp |
| `signer_identity` | TEXT | Fulcio SAN from the delegation event |
| `sequence_num` | INTEGER | Chain sequence number of the delegation event |

### TTL and Scope

- Default TTL: 4 hours (14400 seconds).
- Configurable via `DOCKTAP_DELEGATION_TTL_SECONDS` environment variable.
- Scope: list of allowed operation types (subset of `pull`, `create`, `start`, `stop`, `rm`).
- Operations outside scope or beyond TTL are rejected at the authorization gate.
- Expired delegations are cleaned up periodically by `cleanup_expired_delegations()`.

### Verification

Chain verification annotates each event with an independent `delegation_status` field:

- `origin` — the event is a `session.delegation` event itself.
- `proven` — the event references a valid delegation within scope and TTL.
- `expired` — the event references a delegation but exceeds `expires_at`.
- `scope_violation` — the event's operation type is not in the delegation's scope.
- `missing` — the event references a `delegation_id` that cannot be found on the chain.
- `not_applicable` — the event does not reference a delegation.

This is independent of the existing `owner_status` annotation.

## Logging Semantics

Docktap and TruCon now expose two different Rekor-observability layers on purpose:

- Docktap logs `TruCon commit accepted ... initial_bundle_rekor_uuid=... initial_bundle_rekor_log_index=...` once the locally signed DSSE bundle has been accepted for queueing.
- Those `initial_bundle_rekor_*` fields come from the bundle created during Docktap-side signing and should be read as pre-confirmation identifiers.
- TruCon later logs `confirmed_rekor_log_id=... confirmed_rekor_uuid=... confirmed_rekor_log_index=...` after the asynchronous immutable-backend confirmation completes.
- For operators debugging runtime history, the Docktap log answers "what bundle did Docktap submit", while the TruCon confirmation log answers "what public Rekor record was finally confirmed".

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
3. Multi-resource name/probe checks that may happen before create or reuse decisions:
  - `GET /v*/networks/<name>`
  - `GET /v*/volumes/<name>`
  - `GET /v*/plugins/<name>/json`
4. Pull missing image:
  - `POST /v*/images/create?fromImage=<image>&tag=<tag>`
5. Create container from image:
  - `POST /v*/containers/create?name=<container>`
6. Start container:
  - `POST /v*/containers/<id>/start`
7. Observe and manage runtime:
  - common inspect/list/status calls such as `GET /v*/containers/json` and `GET /v*/containers/<id>/json`
  - explicit log observations such as `GET /v*/containers/<id>/logs`
  - explicit exec observations such as `POST /v*/containers/<id>/exec` and `POST /v*/exec/<id>/start`
  - optional wait/logs calls such as `POST /v*/containers/<id>/wait`
8. Stop and remove lifecycle:
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

### Parent Linking Expectations

Relationship linking in the tracker follows these rules:

- `create` links to the most recent matching `pull` for the image.
- `start`, `stop`, and `rm` link to the matching `create` for the container.
- `container_list` remains a read-only observation type and does not become a parent in the core lifecycle chain.
- `container_logs` remains a read-only observation type and does not become a parent in the core lifecycle chain.
- `network_inspect`, `volume_inspect`, and `plugin_inspect` remain read-only observation types and do not become parents in the core lifecycle chain.
- `exec_create` and `exec_start` remain read-only observation types and do not become parents in the core lifecycle chain.
- `inspect` and `unknown` operations are recorded but typically do not become chain
  parents in the core pull/create/start/stop/rm lifecycle.

Container-list requests may preserve query metadata such as `all`, `limit`, `filters`, `before`, and `since` in the operation record so `docker ps` and `docker ps -a` style scans remain distinguishable without changing lifecycle semantics.

Resource-probe observations preserve resource-family intent without changing lifecycle semantics: `image_inspect`, `network_inspect`, `volume_inspect`, and `plugin_inspect` identify which family Docker probed during preflight or multi-resource name resolution.

For those four observation types, Docktap records a local `response.outcome` field with the first-wave values `ok`, `miss`, and `error`. A daemon `404` maps to `miss` only for those explicit probe observations. Proxy-local synthesized failures, malformed-request responses, and other non-benign statuses remain `error` and stay distinguishable from daemon-level misses through the recorded response metadata.

Container detail `inspect` remains outside this benign-miss policy. A `GET /containers/{id}/json` `404` is still treated as a deferred boundary rather than reclassified as a normal probe miss.

Container log reads now sit outside the generic fallback bucket: `container_logs` identifies `GET /containers/{id}/logs` as explicit read-only observation traffic while preserving the existing streaming timeout rules for logs endpoints.

The remaining `unknown` bucket should be read as a documented defer boundary, not accidental classifier overflow. Current deferred read-only examples include `GET /events`, `GET /containers/{id}/stats`, `GET /containers/{id}/top`, and `GET /exec/{id}/json`, which need separate proposals before they receive stable observation labels.

Exec-path observations preserve minimal identifiers for trace readability: `exec_create` retains the target `container_id`, and `exec_start` retains the target `exec_id` from the API path. Follow-up exec inspection such as `GET /exec/<id>/json` remains intentionally deferred in the current taxonomy.

### Daemon-Internal Phase Taxonomy

The request classification model above covers the HTTP API observation plane only. Mixed Docker traces can also include a second observation plane made up of daemon/runtime-internal phases that are not inferred from `get_operation_type(method, path)` alone.

This daemon-internal taxonomy is complementary to the API-path model:

- API-path observations describe what the Docker client asked the daemon to do.
- Daemon/internal phases describe what the daemon and runtime stack did internally while carrying out that work.
- The second plane does not replace request classification, parent-linking, or `SUBMITTABLE_OPERATIONS`.

Docktap's first documentation-level daemon/internal taxonomy uses five top-level phase families:

- `storage/mount`: layer-store and rootfs preparation work such as overlay mounts before a container starts running.
- `runtime-spec/bundle`: OCI bundle creation, cgroup/runtime-spec preparation, and related launch setup.
- `task lifecycle`: runtime task transitions for containers and exec flows such as create, start, and exit.
- `attach/stream`: transport-facing stream attachment activity such as stdout/stderr begin/end and attach completion.
- `housekeeping`: daemon maintenance work such as exec cleanup and similar non-primary lifecycle follow-up activity.

Representative mappings from `openclaw-docker-analysis.md`:

| Mixed-trace example | Phase family | Why it belongs there |
|---|---|---|
| `container mounted via layerStore` | `storage/mount` | The daemon is preparing the container filesystem view before runtime execution. |
| `bundle dir created`, `createSpec: cgroupsPath` | `runtime-spec/bundle` | These lines describe OCI/runtime launch preparation rather than an external API request. |
| `topic=/tasks/create`, `topic=/tasks/start`, `topic=/tasks/exec-added`, `topic=/tasks/exec-started`, `topic=/tasks/exit` | `task lifecycle` | These lines reflect containerd runtime state transitions for containers and exec tasks. |
| `attach: stdout: begin`, `attach: stderr: end`, `attach done` | `attach/stream` | These lines describe stream attachment lifecycle rather than workload lifecycle state. |
| `clean 2 unused exec commands` | `housekeeping` | The daemon is performing background cleanup after runtime activity has completed. |

Healthcheck-driven exec activity is intentionally not a separate top-level family in this first taxonomy. It is better understood as a cross-cutting source context that can appear inside `task lifecycle` and `attach/stream` phases.

The defer boundary is explicit:

- This taxonomy does not define a canonical event schema for daemon/internal phases.
- This taxonomy does not define how daemon/internal phases join back to API requests, container IDs, or exec IDs.
- This taxonomy does not distinguish healthcheck-driven exec activity from foreground workload exec activity.
- This taxonomy does not define which housekeeping patterns should later become alerts or anomaly signals.

Those concerns belong to later GAP-22 tasks covering task normalization, API/internal correlation, healthcheck interpretation, and housekeeping guidance.

### Normalized Task-Transition Model

Within the daemon/internal `task lifecycle` family, Docktap now also defines a documentation-level normalized task-transition contract for mixed-trace analysis. This contract is still observational and documentation-first: it does not introduce a parser, an ingestion surface, or a cross-plane join model.

The first-wave normalized transition set is:

- `tasks/create`
- `tasks/start`
- `tasks/exec-added`
- `tasks/exec-started`
- `tasks/exit`

These transitions should be read as normalized daemon/internal observations rather than as higher-level Docker API operations:

- `tasks/create` and `tasks/start` are container-task transitions inside the runtime path that follows Docker `create` and `start`, but they are not the same thing as the HTTP `create` and `start` operations themselves.
- `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit` are exec-task transitions inside the runtime path, but they are not the same thing as the API-plane `exec_create` and `exec_start` observations.

The minimum canonical daemon/internal facts for a normalized task transition are:

- `topic`
- `timestamp`
- `source namespace`
- `container identity`
- `exec identity` when reliable exec-specific evidence is available in the trace

This first normalized contract keeps container-task and exec-task transitions distinguishable while leaving them inside the same top-level `task lifecycle` family:

| Normalized transition shape | Representative mixed-trace evidence | Minimum facts that matter |
|---|---|---|
| container-task transition | `topic=/tasks/create`, `topic=/tasks/start`, `namespace=moby`, `for container 9d7fe898...` | topic, timestamp, namespace, container identity |
| exec-task transition | `starting exec command 7c740719... in container 3d2eb9f3...`, then `topic=/tasks/exec-added`, `topic=/tasks/exec-started`, `topic=/tasks/exit` | topic, timestamp, namespace when present, container identity, exec identity when available |

The required-versus-supplemental boundary is also explicit:

- `tasks/create` and `tasks/start` are the required normalized task transitions for minimal cold-start interpretation.
- `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit` are supplemental transitions for richer runtime analysis after cold start.

The defer boundary remains explicit here as well:

- This normalized task-transition model does not define API-path to daemon/internal correlation rules.
- This normalized task-transition model does not decide whether an exec path is healthcheck-driven or foreground workload activity.
- This normalized task-transition model does not define attach-stream semantics.
- This normalized task-transition model does not define a parser or ingestion implementation.

### API-To-Internal Correlation Contract

Docktap now also defines a documentation-first correlation contract between the API-path observation plane and the normalized daemon/internal transition plane. This contract is intended for mixed-trace interpretation: it describes how operators should relate API observations to normalized internal runtime activity, but it does not define parser implementation or verifier-style proof rules.

The primary correlation shapes are:

- container create correlation: API-plane `create` observations join to the internal preparation sequence that may include `storage/mount`, `runtime-spec/bundle`, and the follow-on container-task setup that leads toward `tasks/create`
- container start correlation: API-plane `start` observations join to the runtime preparation and task-lifecycle sequence that leads to `tasks/start`
- exec correlation: API-plane `exec_create` and `exec_start` observations join to the normalized exec-task sequence built from `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit`

These are cross-plane joins, not reclassifications:

- API observations remain the client-facing request record.
- Normalized internal transitions remain daemon/internal runtime observations.
- Correlation explains how one mixed trace can be read as a single runtime story across those two planes.

Docktap's first-wave correlation evidence is intentionally tiered:

| Evidence tier | Typical evidence | How to interpret it |
|---|---|---|
| strong | full `container identity`, `exec identity` | Canonical join evidence when the trace exposes the same runtime object across both planes. |
| contextual | `timestamp` proximity, `source namespace`, operation shape, adjacent runtime preparation | Useful correlation support when strong identifiers are incomplete or only partially visible. |
| fallback | container name references, short-ID mentions, nearby bundle or runtime-prep context | Heuristic guidance for mixed-trace reading, not canonical proof by itself. |

This contract also preserves non-1:1 outcomes:

- one API observation may correlate to multiple daemon/internal transitions
- one internal sequence may be understood through multiple API-plane observations
- some joins may remain `inferred` or `unresolved` when trace evidence is incomplete

Representative mixed-trace correlation shapes from `openclaw-docker-analysis.md`:

| API-path observation | Correlated normalized internal transitions | Evidence that supports the join |
|---|---|---|
| `POST /containers/create` | storage or mount preparation, then container-task setup leading toward `tasks/create` | time adjacency, container identity, nearby runtime-prep context |
| `POST /containers/<id>/start` | runtime-spec or bundle preparation, then `tasks/start` | time adjacency, container identity, bundle and namespace context |
| `POST /containers/<id>/exec` plus `POST /exec/<id>/start` | `tasks/exec-added`, `tasks/exec-started`, `tasks/exit` | exec identity when present, container identity, local sequence order |

The defer boundary stays explicit:

- This correlation contract does not define parser or ingestion implementation.
- This correlation contract does not decide whether an exec flow is healthcheck-driven or foreground workload activity.
- This correlation contract does not define attach-stream semantics beyond optional correlation context.
- This correlation contract does not define housekeeping anomaly guidance.

### Secondary Runtime Interpretation Contract

Docktap now also defines a documentation-first interpretation contract for healthcheck-like exec flows and attach activity after a mixed trace has already been normalized and correlated. This layer is intentionally operator-facing: it explains how to read daemon-generated secondary runtime activity without redefining the normalized exec-task model or turning the current docs into a parser specification.

The first-wave interpretation model starts from a conservative distinction:

- primary workload lifecycle activity covers the main container create and start path and similar workload-facing runtime changes
- secondary runtime activity covers daemon-generated or daemon-managed exec flows that should not be mistaken for the primary workload path
- healthcheck-like interpretation is a stronger reading inside secondary runtime activity when the trace exposes enough supporting evidence

The required runtime spine for a healthy healthcheck-like flow remains the normalized exec-task sequence:

- `tasks/exec-added`
- `tasks/exec-started`
- `tasks/exit`

Those runtime transitions are the required evidence for the first-wave sequence. Other cues remain contextual rather than universally required:

- `attach: stdout begin/end`
- `attach: stderr begin/end`
- `attach done`
- explicit healthcheck start or result lines such as `Running health check for container ...` and `Health check ... done (exitCode=0)`
- repeated cadence against the same container when the trace shows periodic healthcheck execution

Attach lines are interpreted as a transport envelope around the exec flow rather than as workload lifecycle states:

- `attach: stdout/stderr begin` indicates stream attachment around the exec path
- `attach: stdout/stderr end` indicates stream closure around that same exec path
- `attach done` indicates transport completion for the attached exec flow, not the workload lifecycle completion event itself

Representative healthy secondary-runtime shape from `openclaw-docker-analysis.md`:

| Mixed-trace evidence | How to read it |
|---|---|
| `Running health check for container ...` -> `starting exec command ...` -> `tasks/exec-added` -> `tasks/exec-started` -> `tasks/exit` -> `attach done` -> `Health check ... done (exitCode=0)` | A healthcheck-like secondary runtime flow built on the normalized exec-task spine, with attach lines and result text acting as contextual evidence around the exec sequence. |

The first-wave anomalous secondary-runtime shapes are intentionally narrow:

- repeated exec failures inside a recurring healthcheck-like path
- `tasks/exec-started` without a corresponding exit in the observed local sequence
- attach begin lines without matching attach completion cues

The defer boundary remains explicit here too:

- This interpretation contract does not define parser or machine confidence implementation.
- This interpretation contract does not force binary healthcheck-versus-foreground decisions when evidence is incomplete.
- This interpretation contract does not define post-exec cleanup or maintenance guidance.
- Cleanup lines such as `clean 2 unused exec commands` remain housekeeping concerns for later GAP-22 work.

### Housekeeping And Internal-Maintenance Interpretation Contract

Docktap now also defines a documentation-first interpretation contract for daemon/internal housekeeping activity that appears after primary lifecycle work and secondary runtime activity have already completed. This layer is intentionally narrow in the first wave: it explains how to read post-runtime maintenance context in mixed traces without redefining runtime paths, parser behavior, or Docktap-local cleanup logic.

The first-wave housekeeping model starts from three boundaries:

- housekeeping is post-runtime maintenance context, not a primary workload lifecycle path
- housekeeping is distinct from secondary runtime exec activity such as healthcheck-like flows
- housekeeping is distinct from Docktap-local retention, retry cleanup, and sidecar sweeper behavior

The first-wave evidence anchor is intentionally conservative:

- post-exec cleanup lines such as `clean 2 unused exec commands`
- similarly narrow maintenance residue that appears after nearby exec or runtime activity finishes

Broader maintenance families remain extension room rather than fully specified first-wave contract surface:

- image GC
- background scanning
- retry or reconcile loops

Housekeeping interpretation is contextual-first rather than object-precise in the first wave:

- strong container or exec identifiers may be unavailable on housekeeping lines themselves
- local sequence order, timing proximity, and surrounding runtime context may still be sufficient to interpret the line as daemon maintenance
- lack of an object-precise join does not by itself invalidate housekeeping interpretation

Representative first-wave housekeeping shape from `openclaw-docker-analysis.md`:

| Mixed-trace evidence | How to read it |
|---|---|
| `Running health check for container ...` -> `starting exec command ...` -> `tasks/exec-added` -> `tasks/exec-started` -> `tasks/exit` -> `attach done` -> `Health check ... done (exitCode=0)` -> about 22 seconds later `clean 2 unused exec commands` | The healthcheck-like exec flow is secondary runtime activity; the later cleanup line is best read as bounded post-runtime housekeeping noise rather than as a new workload lifecycle transition or a continuation of the exec path. |

The first-wave signal boundary is intentionally minimal:

- limited delayed cleanup after nearby runtime activity is expected maintenance noise by default
- repeated, unusually dense, or persistently delayed housekeeping that starts to obscure the surrounding runtime story is worth later investigation

The defer boundary remains explicit here too:

- This interpretation contract does not define parser or machine confidence implementation.
- This interpretation contract does not define threshold-based alerting or a full anomaly model for maintenance activity.
- This interpretation contract does not redefine Docktap-local retention, retry cleanup, or sidecar GC behavior.
- Broader maintenance coverage beyond exec-cleanup-style evidence remains future GAP-22 work.

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

Docktap validation is split across three layers:

- repository-level service and smoke validation documented in `docs/TESTING.md`
- focused Docktap proxy and lifecycle scenarios exercised through the Docktap test harness in `tc_api/docktap/test_suite.py`
- architecture-level mixed-trace interpretation captured in this document and the related analysis references

This document does not duplicate concrete test commands. Use `docs/TESTING.md` as the supported operator entrypoint.

## Operational Notes

- For test automation and current proxy behavior validation, use `stream_test.py` indirectly via `test_suite.py`.
- Keep tracker and parsing logic in `proxy/operation_log.py` to avoid duplicate behavior across runtimes.
- Keep engine-specific request normalization in `proxy/runtime_adapter.py` so TruCon commit logic and verifier-facing event semantics remain canonical.
- `stream_test.py` and `main.py` now share behavior through `DockerProxyServer.handle_client`.
- Docktap local state is operational cache and short-lived diagnostics only. Replay correctness comes from TruCon and immutable backends, not from Docktap-local retention.
- A background sweeper periodically removes expired operation records, removed-container mappings, and resolved retry records while preserving retryable items until they are acknowledged or terminally exhausted.
