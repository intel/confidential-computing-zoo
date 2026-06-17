## Why

Docktap currently does not give `GET /containers/json` its own observation type, so `docker ps` and `docker ps -a` style scans are folded into generic container inspection behavior. That makes control-plane traces harder to interpret and obscures a high-frequency runtime observation path that appears in real daemon logs.

## What Changes

- Add an explicit read-only observation classification for `GET /containers/json` requests.
- Preserve query parameters such as `all`, `limit`, `filters`, `before`, and `since` as structured metadata for container-list observations.
- Document and test the boundary between container-list observations and container detail inspection.
- Keep lifecycle commit behavior unchanged: no expansion of `SUBMITTABLE_OPERATIONS`, no new parent-chain linkage, and no polling-intent inference.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `sock-bridge-lifecycle-classification`: Extend Docktap's canonical request classification contract so `GET /containers/json` is classified as `container_list` rather than falling into generic container inspection behavior.

## Impact

- Affected code: `docktap/proxy/operation_log.py`, related proxy tests, and Docktap classification documentation.
- Affected APIs: Docker Engine API observation for `GET /containers/json` and `GET /v*/containers/json`.
- Affected systems: Docktap runtime observability, mixed Docker trace interpretation, and downstream log consumers that aggregate by operation type.