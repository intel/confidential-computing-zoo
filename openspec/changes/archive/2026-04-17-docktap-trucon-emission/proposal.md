## Why

Docktap captures Docker runtime events (pull, create, start, stop, rm) but currently only logs them as JSON to stdout. There is zero communication with TruCon — no HTTP calls, no event submission, no signed DSSE bundles. This means runtime container lifecycle events are invisible to the trusted log chain, breaking the architecture's promise that all trust-relevant operations are recorded immutably. This is the highest-priority remaining gap (GAP-01) and unblocks the entire Docktap integration path.

## What Changes

- Add a TruCon commit client inside Docktap that constructs `Entry(key, value)` pairs from Docker operation metadata, signs DSSE bundles using ambient OIDC credentials, and POSTs them to TruCon's `/commit` endpoint.
- Each Docker operation (`pull`, `create`, `start`, `stop`, `rm`) produces one independent TruCon commit.
- Signing shares tc_api's existing infrastructure (`sigstore.oidc.detect_credential()`), with token re-acquired per commit.
- All events target `chain_id="default"` (v1 — per-workload chain assignment deferred to GAP-11).
- Submission is best-effort and synchronous: TruCon failures log a warning but never block the Docker API response back to the CLI.
- Other operation types (`wait`, `rmi`, `image_inspect`, `inspect`, `preflight_ping`, `preflight_info`, `unknown`) are not submitted.

## Capabilities

### New Capabilities
- `docktap-trucon-commit`: Docktap constructs signed DSSE bundles from Docker operation metadata and submits them to TruCon `POST /commit` with best-effort failure handling.

### Modified Capabilities
_None — no existing spec-level requirements change. The TruCon `/commit` endpoint and DSSE signing flow are used as-is._

## Impact

- **Affected code**: `docktap/proxy/docker_proxy.py` (hook after response), `docktap/` (new commit client module).
- **Shared code**: Docktap will import or replicate the DSSE signing path from `src/tc_api/tlog_client.py` (entry digest computation, DSSE statement construction, Sigstore signing). A shared utility or direct import needs to be decided in design.
- **Dependencies**: Requires `sigstore` Python package available in Docktap's runtime environment.
- **Runtime**: Docktap process now makes HTTP calls to TruCon on each intercepted Docker operation. Adds latency to the proxy path (mitigated by best-effort — failures don't block).
- **Testing**: New integration tests needed for concurrent Docktap + REST submissions verifying `sequence_num` ordering on the shared default chain.
