## Why

All Docktap integration code is complete (GAP-01 event emission, GAP-10 service auth, GAP-11 per-workload chain, GAP-03 instance mapping), but Docktap is absent from every deployment artifact. `start.sh` launches only TruCon + tc_api; `docker-compose.yml` defines only `tc-api`, `trucon`, and `nginx` services; `Dockerfile` does not package Docktap as an entrypoint. The runtime interception architecture (architecture.md §4.2, §6.2) is inoperable in any real deployment.

## What Changes

- Add a `docktap` service to `docker-compose.yml` as an independent container sharing the same Docker image, with Docker daemon socket mount, proxy socket volume, health check, and `TRUCON_SERVICE_TOKEN` injection.
- Update `start.sh` to launch Docktap as a third managed background process with PID tracking and graceful shutdown via the existing `trap cleanup` pattern.
- Add a lightweight HTTP health endpoint (`/healthz` on port 8002) to Docktap's `main.py` for container health checks.
- Add a compose `.env` generation step so `TRUCON_SERVICE_TOKEN` is shared across all three containers via `docker compose` environment variable interpolation.
- Document `DOCKER_HOST` configuration for TD VM users (proxy socket path, `/etc/profile.d/docktap.sh` auto-injection).

## Capabilities

### New Capabilities
- `docktap-compose-service`: Docker Compose service definition for Docktap as an independent container with health check, Docker socket mount, proxy socket volume, and service token injection.
- `docktap-bare-metal-launch`: Bare-metal process management for Docktap in `start.sh` — background process launch, PID tracking, and graceful shutdown alongside TruCon and tc_api.
- `docktap-health-endpoint`: Lightweight HTTP `/healthz` endpoint inside Docktap for container and bare-metal health monitoring.

### Modified Capabilities

## Impact

- **Deployment artifacts**: `docker-compose.yml`, `start.sh`, `Dockerfile` (entrypoint/expose changes).
- **Docktap code**: `docktap/main.py` gains a health server thread.
- **Documentation**: README.md updated with `DOCKER_HOST` configuration instructions.
- **Security model**: Docktap down = Docker CLI unavailable (by design — all operations must be recorded).
- **Dependencies**: No new external dependencies. Docktap reuses the existing Docker image.
