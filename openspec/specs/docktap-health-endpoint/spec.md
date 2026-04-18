## ADDED Requirements

### Requirement: HTTP health endpoint on dedicated port
Docktap SHALL run a lightweight HTTP server on a configurable port (default 8002, via `DOCKTAP_HEALTH_PORT` env var) that serves `GET /healthz`.

#### Scenario: Health check returns 200 when running
- **WHEN** Docktap is running and the proxy is accepting connections
- **THEN** `GET http://localhost:8002/healthz` returns HTTP 200 with JSON body `{"status": "ok"}`

#### Scenario: Custom health port
- **WHEN** `DOCKTAP_HEALTH_PORT=9090` is set
- **THEN** the health endpoint listens on port 9090 instead of 8002

### Requirement: Health server runs as daemon thread
The health HTTP server SHALL run as a `threading.Thread(daemon=True)` inside `SockBridge` so it does not prevent process exit and does not interfere with the proxy's main accept loop.

#### Scenario: Health server does not block shutdown
- **WHEN** Docktap receives SIGTERM
- **THEN** the process exits cleanly without waiting for the health server thread

### Requirement: Health server starts before proxy accept loop
The health server thread SHALL be started in `SockBridge.start()` before the proxy begins accepting client connections, so health checks succeed as soon as the service is ready.

#### Scenario: Health available before first Docker request
- **WHEN** Docktap starts up
- **THEN** `/healthz` responds with 200 before any Docker CLI connections are accepted

### Requirement: Health endpoint port exposed in Dockerfile
The `Dockerfile` SHALL include port 8002 in its `EXPOSE` directive alongside 8000 and 8001.

#### Scenario: Port visible in container metadata
- **WHEN** the Docker image is inspected
- **THEN** port 8002 is listed in the exposed ports
