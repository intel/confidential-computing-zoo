## Purpose

Define the requirements for running Docktap as an independent service in the Compose deployment model.

## Requirements

### Requirement: Docktap runs as independent compose service
The `docker-compose.yml` SHALL define a `docktap` service that uses the same Docker image as `tc-api` and `trucon` with a distinct `command:` override to launch Docktap's `main.py`.

#### Scenario: Compose brings up Docktap alongside other services
- **WHEN** operator runs `docker compose up`
- **THEN** three application services start: `tc-api`, `trucon`, and `docktap`
- **THEN** `docktap` container uses the same image as `tc-api`

### Requirement: Docktap mounts Docker daemon socket
The `docktap` service SHALL mount the host's `/var/run/docker.sock` as `/var/run/docker-daemon.sock` inside the container so the proxy can forward requests to the real Docker daemon.

#### Scenario: Docktap forwards Docker API requests
- **WHEN** Docktap container starts with the daemon socket mount
- **THEN** Docktap's proxy server can reach the Docker daemon via `/var/run/docker-daemon.sock`

### Requirement: Proxy socket exposed to host via bind-mount
The `docktap` service SHALL bind-mount a host directory `/var/run/docktap/` into the container. Docktap SHALL create its proxy socket at `/var/run/docktap/docker.sock` so TD VM users can connect via `DOCKER_HOST=unix:///var/run/docktap/docker.sock`.

#### Scenario: Docker CLI connects through proxy socket
- **WHEN** a TD VM user sets `DOCKER_HOST=unix:///var/run/docktap/docker.sock`
- **THEN** Docker CLI commands are routed through Docktap's proxy
- **THEN** operations are intercepted and submitted to TruCon

#### Scenario: Proxy socket visible on host filesystem
- **WHEN** Docktap container is running
- **THEN** the file `/var/run/docktap/docker.sock` exists on the host

### Requirement: Docktap receives TRUCON_SERVICE_TOKEN
The `docktap` service SHALL receive `TRUCON_SERVICE_TOKEN` via compose environment variable interpolation from the `.env` file, identical to how `tc-api` and `trucon` receive it.

#### Scenario: Token shared across all services
- **WHEN** `.env` file contains `TRUCON_SERVICE_TOKEN=<token>`
- **THEN** all three services (`tc-api`, `trucon`, `docktap`) receive the same token value
- **THEN** Docktap can authenticate to TruCon's `/commit` endpoint

### Requirement: Docktap receives TRUCON_URL
The `docktap` service SHALL receive `TRUCON_URL` pointing to the trucon service (e.g., `http://trucon:8001`) so event submissions reach the correct endpoint.

#### Scenario: Docktap connects to TruCon via compose networking
- **WHEN** Docktap starts with `TRUCON_URL=http://trucon:8001`
- **THEN** event submissions from `TruConCommitter` reach the TruCon service

### Requirement: Docktap depends on TruCon service
The `docktap` service SHALL declare `depends_on: trucon` with a healthcheck condition so Docktap starts only after TruCon is healthy.

#### Scenario: Startup ordering enforced
- **WHEN** `docker compose up` is run
- **THEN** TruCon starts and passes healthcheck before Docktap starts

### Requirement: Docktap has restart policy
The `docktap` service SHALL use `restart: unless-stopped` so crashed instances are automatically restarted by Docker.

#### Scenario: Automatic recovery after crash
- **WHEN** Docktap process crashes
- **THEN** Docker compose restarts the container automatically

### Requirement: Compose healthcheck for Docktap
The `docktap` service SHALL define a `healthcheck` using `curl` against the `/healthz` endpoint on port 8002.

#### Scenario: Compose detects unhealthy Docktap
- **WHEN** Docktap's `/healthz` endpoint stops responding
- **THEN** Docker compose marks the service as unhealthy

### Requirement: Token pre-generation for compose
A mechanism (documented script or `start.sh` integration) SHALL generate `TRUCON_SERVICE_TOKEN` and write it to `.env` before `docker compose up` so all services share the same token.

#### Scenario: Token generated before compose up
- **WHEN** operator follows deployment instructions
- **THEN** `.env` file contains a freshly generated `TRUCON_SERVICE_TOKEN`
- **THEN** `docker compose up` interpolates the token into all service environments
