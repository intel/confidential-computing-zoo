## Why

Docktap's runtime observation classifier now covers the main preflight, exec, and resource-probe paths, but common read-only endpoints still fall into a generic `unknown` bucket. That makes mixed Docker traces harder to read and leaves the remaining classifier boundary implicit instead of documented.

## What Changes

- Add explicit observation classification for at least `GET /v*/containers/{id}/logs` so common high-frequency read-only traffic no longer appears as generic `unknown`.
- Document which runtime observation endpoints remain intentionally deferred in the `unknown` bucket so the fallback becomes a conscious boundary.
- Preserve the current separation between read-only observation types and trusted lifecycle commit types.
- Keep `SUBMITTABLE_OPERATIONS` unchanged and limit this change to observation-model clarity rather than trusted-event scope expansion.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `sock-bridge-lifecycle-classification`: extend the Docktap observation classification contract so common read-only endpoints such as container logs are labeled explicitly and the remaining `unknown` bucket is documented as an intentional boundary.

## Impact

- Affected code: `docktap/proxy/operation_log.py`, focused classifier tests under `docktap/tests/`, and Docktap architecture/API mapping docs.
- Affected APIs: Docker Engine API observation for `GET /v*/containers/{id}/logs` and any explicitly documented deferred read-only endpoints kept in `unknown`.
- Affected systems: Docktap local observability, operator interpretation of mixed runtime traces, and future GAP-22 daemon/internal-phase work that depends on a cleaner API-path observation plane.