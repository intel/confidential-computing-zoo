## 1. Health Endpoint

- [x] 1.1 Add HTTP health server thread to `docktap/main.py` — create a `HealthHandler` class and `start_health_server(port)` function that runs `http.server.HTTPServer` as a daemon thread serving `GET /healthz` with `{"status": "ok"}` JSON response
- [x] 1.2 Start health server in `SockBridge.start()` before the proxy accept loop, using `DOCKTAP_HEALTH_PORT` env var (default 8002)
- [x] 1.3 Add port 8002 to `EXPOSE` directive in `Dockerfile`

## 2. Docker Compose Service

- [x] 2.1 Add `docktap` service to `docker-compose.yml` — same image as `tc-api`, `command:` override to run `python -m docktap.main`, environment variables (`TRUCON_URL`, `TRUCON_SERVICE_TOKEN`, `DOCKER_SOCKET`, `SOCK_BRIDGE_SOCKET`), `depends_on: trucon` with healthcheck condition, `restart: unless-stopped`
- [x] 2.2 Add volume mounts for `docktap` service — bind-mount `/var/run/docker.sock` as `/var/run/docker-daemon.sock` (daemon) and `/var/run/docktap` as `/var/run/docktap` (proxy socket)
- [x] 2.3 Add healthcheck for `docktap` service — `curl -f http://localhost:8002/healthz`
- [x] 2.4 Add `TRUCON_SERVICE_TOKEN=${TRUCON_SERVICE_TOKEN}` to environment blocks of all three services (`tc-api`, `trucon`, `docktap`) for `.env` file interpolation

## 3. Bare-Metal Launch (start.sh)

- [x] 3.1 Add `DOCKTAP_SOCKET` env var with default `/var/run/docktap/docker.sock` and create socket directory with `mkdir -p`
- [x] 3.2 Launch Docktap as background process after TruCon — `python -m docktap.main --socket-path $DOCKTAP_SOCKET --docker-socket-path /var/run/docker.sock &`, capture `DOCKTAP_PID`, verify startup with `kill -0`
- [x] 3.3 Extend `cleanup` trap function to send SIGTERM to `DOCKTAP_PID` alongside `TRUCON_PID`

## 4. Token Generation for Compose

- [x] 4.1 Add token pre-generation logic — if `.env` does not contain `TRUCON_SERVICE_TOKEN`, generate and append it before `docker compose up`. Document in README.md as part of deployment instructions.

## 5. Documentation

- [x] 5.1 Add Docktap deployment section to README.md — compose instructions, `DOCKER_HOST` configuration, `/etc/profile.d/docktap.sh` example
- [x] 5.2 Document environment variables: `DOCKTAP_SOCKET`, `DOCKTAP_HEALTH_PORT`, `DOCKER_SOCKET`, `SOCK_BRIDGE_SOCKET`

## 6. Testing

- [x] 6.1 Verify compose service starts: `docker compose up -d` and confirm all three services reach healthy state
- [x] 6.2 Verify bare-metal launch: `bash start.sh` and confirm Docktap PID is alive, health endpoint responds, and cleanup stops all processes
- [x] 6.3 Verify Docker CLI through proxy: set `DOCKER_HOST`, run `docker info`, confirm Docktap logs the operation
