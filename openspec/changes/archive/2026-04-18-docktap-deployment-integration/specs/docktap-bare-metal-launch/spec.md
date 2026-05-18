## ADDED Requirements

### Requirement: Docktap launched as background process
`start.sh` SHALL launch Docktap as a background process after TruCon and before tc_api, using the same pattern as TruCon (background `&`, PID capture, readiness check).

#### Scenario: Three-process launch order
- **WHEN** operator runs `bash start.sh`
- **THEN** TruCon starts first (port 8001)
- **THEN** Docktap starts second (proxy socket + health port 8002)
- **THEN** tc_api starts last as the foreground process (port 8000)

### Requirement: Docktap PID tracked for cleanup
`start.sh` SHALL capture Docktap's PID in a variable (e.g., `DOCKTAP_PID`) and include it in the existing `cleanup` trap function so Docktap receives SIGTERM on script exit.

#### Scenario: Graceful shutdown includes Docktap
- **WHEN** operator presses Ctrl+C or the script receives SIGTERM
- **THEN** the cleanup function sends SIGTERM to both Docktap and TruCon PIDs
- **THEN** the script waits for both processes to exit

### Requirement: Docktap startup validation
`start.sh` SHALL verify Docktap started successfully (e.g., `kill -0 $DOCKTAP_PID`) after a brief wait, and exit with error if Docktap failed to start.

#### Scenario: Docktap fails to start
- **WHEN** Docktap process exits immediately after launch
- **THEN** `start.sh` prints an error message and exits with non-zero status

### Requirement: Docktap environment variables set
`start.sh` SHALL export `TRUCON_URL`, `TRUCON_SERVICE_TOKEN`, `SOCK_BRIDGE_SOCKET`, and `DOCKER_SOCKET` environment variables before launching Docktap, using the same token already generated for TruCon.

#### Scenario: Token reused across processes
- **WHEN** `start.sh` generates `TRUCON_SERVICE_TOKEN` for TruCon
- **THEN** the same token value is inherited by the Docktap child process
- **THEN** Docktap can authenticate to TruCon

### Requirement: Configurable proxy socket path
`start.sh` SHALL use a configurable proxy socket path via `DOCKTAP_SOCKET` environment variable with a default of `/var/run/docktap/docker.sock`.

#### Scenario: Custom socket path
- **WHEN** operator sets `DOCKTAP_SOCKET=/tmp/my-proxy.sock` before running `start.sh`
- **THEN** Docktap listens on `/tmp/my-proxy.sock`

#### Scenario: Default socket path
- **WHEN** `DOCKTAP_SOCKET` is not set
- **THEN** Docktap listens on `/var/run/docktap/docker.sock`

### Requirement: Socket directory created on startup
`start.sh` SHALL create the proxy socket directory (e.g., `/var/run/docktap/`) with appropriate permissions before launching Docktap.

#### Scenario: Directory does not exist
- **WHEN** `/var/run/docktap/` does not exist
- **THEN** `start.sh` creates the directory before launching Docktap
