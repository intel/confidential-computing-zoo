## Context

Docktap is a Docker Unix socket proxy sidecar that intercepts Docker API traffic, captures operation metadata, and submits signed DSSE bundles to TruCon for trusted event recording. All integration code is complete and tested:

- GAP-01: Event emission to TruCon (`docktap/trucon_client.py`)
- GAP-10: Service auth via Bearer token (`TRUCON_SERVICE_TOKEN`)
- GAP-11: Per-workload chain assignment via container labels
- GAP-03: Instance mapping via `instance_id` on `CommitRequest`

Current deployment artifacts (`start.sh`, `docker-compose.yml`, `Dockerfile`) only launch TruCon and tc_api. Docktap has no deployment path. The existing `docker-compose.yml` already separates tc_api and trucon into independent containers sharing a single Docker image with different `command:` overrides.

Docktap's `main.py` defines `SockBridge` which starts `DockerProxyServer` on a configurable Unix socket and forwards to the real Docker daemon socket. It reads `TRUCON_URL` and `TRUCON_SERVICE_TOKEN` from environment variables.

## Goals / Non-Goals

**Goals:**
- Docktap deployable via both `docker compose up` and `bash start.sh` with zero additional user setup beyond `DOCKER_HOST` configuration.
- Health monitoring for Docktap in both deployment paths.
- `TRUCON_SERVICE_TOKEN` shared across all three services without shared volumes or SQLite.
- TD VM users can use Docker CLI transparently through the proxy.

**Non-Goals:**
- Bypass mechanism when Docktap is down (security model: all operations must be recorded).
- Separate lightweight Docker image for Docktap (reuses existing image).
- Preventing users from unsetting `DOCKER_HOST` to bypass the proxy (can be addressed later with socket permissions).
- Automated `/etc/profile.d/` injection (documented for operators to configure manually).

## Decisions

### D1: Independent container using shared image (Compose)

Docktap runs as a third `docker-compose` service using the same Docker image as tc-api and trucon, with a different `command:` override. This matches the existing pattern where trucon uses `command: ["python", "-m", "uvicorn", ...]`.

**Alternative considered**: Same container as tc_api with a third process. Rejected because it couples failure domains and complicates process management inside a single container.

**Alternative considered**: Separate Dockerfile/image for Docktap. Rejected because Docktap imports `tlog.types` plus tc_api trust/identity helpers, requiring the `tc_api` package and sibling `tlog` package. Using the same image is simpler and images are deduplicated on the same host.

### D2: Proxy socket via bind-mount directory

Docktap creates its proxy socket at `/var/run/docktap/docker.sock` inside the container. A host directory `/var/run/docktap/` is bind-mounted into the Docktap container so the socket is accessible from the TD VM host.

```yaml
docktap:
  volumes:
    - /var/run/docker.sock:/var/run/docker-daemon.sock  # real daemon
    - /var/run/docktap:/var/run/docktap                 # proxy socket exposed to host
  environment:
    - DOCKER_SOCKET=/var/run/docker-daemon.sock
    - SOCK_BRIDGE_SOCKET=/var/run/docktap/docker.sock
```

Users configure `DOCKER_HOST=unix:///var/run/docktap/docker.sock` to route through the proxy. Documentation will describe placing this in `/etc/profile.d/docktap.sh` for auto-injection.

**Alternative considered**: Docker named volume instead of bind-mount. Rejected because named volumes don't expose Unix sockets to the host filesystem reliably across Docker versions.

**Alternative considered**: Socket replacement (rename `/var/run/docker.sock`, symlink proxy socket in its place). Rejected because it requires modifying the host's Docker daemon socket path, which is invasive and hard to reverse.

### D3: Token sharing via compose `.env` file

A wrapper script (or `start.sh` itself) generates `TRUCON_SERVICE_TOKEN` and writes it to a `.env` file. `docker compose` natively reads `.env` and interpolates `${TRUCON_SERVICE_TOKEN}` into all three service environment blocks.

```bash
# Pre-compose token generation
export TRUCON_SERVICE_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "TRUCON_SERVICE_TOKEN=$TRUCON_SERVICE_TOKEN" >> .env
docker compose up
```

For `start.sh` (bare-metal), the existing pattern of `export TRUCON_SERVICE_TOKEN=...` before spawning child processes continues to work.

**Alternative considered**: Shared SQLite database on tmpfs volume. Rejected because adding a database for a single secret is over-engineered, requires startup ordering/polling, and provides no security benefit over environment variable injection.

**Alternative considered**: Docker secrets. Rejected because Docker secrets require Swarm mode, which is not a deployment requirement.

### D4: Health endpoint as daemon thread on port 8002

A minimal HTTP server runs as a `threading.Thread(daemon=True)` inside `SockBridge`, listening on port 8002 and serving `GET /healthz` with a 200 response. This matches Docktap's existing thread-per-connection concurrency model.

The health response includes basic status information:
```json
{"status": "ok", "proxy_socket": "/var/run/docktap/docker.sock"}
```

Compose healthcheck:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8002/healthz"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

### D5: Bare-metal launch pattern in start.sh

Docktap is launched as a third background process in `start.sh`, after TruCon and before tc_api (since tc_api is the foreground blocking process). The PID is tracked and the `cleanup` trap is extended to stop Docktap on exit.

Launch order: TruCon → Docktap → tc_api (foreground).

Docktap starts after TruCon because it needs `TRUCON_URL` to be reachable for event submission (though failures are best-effort and non-blocking).

### D6: Docktap failure model

Docktap down = Docker CLI unavailable. This is by design: all Docker operations must pass through the proxy for trusted event recording. `restart: unless-stopped` in compose and process supervision in bare-metal ensure automatic recovery.

## Risks / Trade-offs

- **[Proxy socket cleanup on crash]** → If Docktap crashes, the stale Unix socket file may prevent restart. Mitigation: Docktap's `SockBridge.start()` already calls `os.unlink()` on the socket path before binding. Compose `restart: unless-stopped` handles automatic recovery.

- **[Port 8002 conflict]** → The health endpoint port could conflict with other services. Mitigation: Make it configurable via `DOCKTAP_HEALTH_PORT` env var with 8002 as default. Expose in compose and Dockerfile.

- **[Startup ordering]** → Docktap submits events to TruCon; if TruCon isn't ready, initial submissions fail. Mitigation: Docktap already uses best-effort submission (warnings, no blocking). Compose `depends_on` with healthcheck ensures ordering.

- **[DOCKER_HOST not set]** → If a user doesn't configure `DOCKER_HOST`, Docker CLI bypasses the proxy. Mitigation: Documentation plus a startup log message in Docktap. Full enforcement (socket permissions) deferred to future work.
