## Context

TruCon is the single-instance sequencer that serializes RTMR extends, SQLite inserts, and chain state updates. It currently exposes five HTTP endpoints on `127.0.0.1:8001` with no authentication. Two callers exist:

1. **tc_api** (`src/tc_api/tlog_client.py`) — uses `urllib.request` to POST signed DSSE bundles and GET status/state/verification.
2. **Docktap** (`docktap/trucon_client.py`) — uses `urllib.request` to POST Docker lifecycle events.

Both callers run on the same CVM. The threat model target is preventing unauthorized processes on the same VM from injecting events into the trust chain.

## Goals / Non-Goals

**Goals:**
- Reject unauthenticated requests to all TruCon endpoints with `401 Unauthorized` + descriptive error.
- Single shared `TRUCON_SERVICE_TOKEN` environment variable used by tc_api and Docktap.
- Token generated at CVM startup, session-scoped (lifetime = VM lifetime).
- Development/test bypass via `TRUCON_AUTH_DISABLED=true` with startup warning.
- Constant-time token comparison to prevent timing attacks.

**Non-Goals:**
- Per-caller identity differentiation (tc_api vs Docktap are not distinguished by token; event source is already distinguishable via DSSE `event_type` prefix).
- Token rotation during a running session.
- mTLS or Unix socket peer credentials (deferred to future change; recorded in `overview_tasks.md`).
- Rate limiting or request throttling.
- Authorization (role-based access) — all authenticated callers have equal access.

## Decisions

### D1: Shared Bearer Token (Phase A)

**Choice**: Single `TRUCON_SERVICE_TOKEN` env var, transmitted as `Authorization: Bearer <token>`.

**Alternatives considered**:
- *Per-caller tokens*: Would allow TruCon to distinguish source, but event_type already provides this signal. Two tokens doubles operational burden for no security gain.
- *mTLS*: Strongest option but requires certificate management infrastructure that doesn't exist. Deferred to Phase B.
- *Unix socket peer credentials (SO_PEERCRED)*: Elegant for same-machine, but requires changing TruCon from TCP to Unix socket listener, impacting all callers and tests. Deferred to Phase B.

**Rationale**: Simplest mechanism that satisfies the threat model (block unauthorized localhost processes). Upgrade path to stronger mechanisms is preserved.

### D2: All Endpoints Authenticated

**Choice**: A single FastAPI middleware checks `Authorization: Bearer <token>` on every request.

**Alternatives considered**:
- *Write-only auth (POST /commit)*: Simpler, but chain-state and verification endpoints also expose sensitive data (event digests, MR values). Inconsistent policy surface increases misconfiguration risk.

**Rationale**: One middleware, zero routing exceptions, zero confusion about which endpoints need tokens. If external verifiers later need anonymous access, a dedicated read-only endpoint can be added.

### D3: Token Generation at Startup

**Choice**: `start.sh` (or `trust_service.sh`) generates token via `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` and exports `TRUCON_SERVICE_TOKEN`. All child processes inherit it.

**Rationale**: CVM disk is untrusted (architecture constraint), so file-based secrets are ruled out. Environment variable inheritance within the same process tree is the standard pattern for CVM-scoped secrets. Token lifetime matches VM lifetime — acceptable because a VM reboot destroys the RTMR chain and SQLite queue anyway.

### D4: Development Mode Bypass

**Choice**: When `TRUCON_AUTH_DISABLED=true` is set, skip token validation entirely. TruCon logs a `WARNING`-level banner at startup: `"⚠ TruCon service authentication DISABLED — development mode only"`.

**Rationale**: ~10 lines of code. Avoids test infrastructure having to manage tokens. `run_tests.sh` and test fixtures set this var. Production deployments never set it (start.sh generates a real token instead).

### D5: 401 Response Format

**Choice**: Return `401 Unauthorized` with JSON body `{"detail": "<reason>"}` where reason is one of:
- `"Missing Authorization header"`
- `"Invalid Authorization scheme, expected Bearer"`
- `"Invalid service token"`

**Rationale**: Descriptive errors help debugging in CVM environments where interactive debugging is limited. No security-sensitive information is leaked — the error messages don't reveal the expected token value.

## Risks / Trade-offs

- **[Token in environment variable]** → Process listing (`/proc/*/environ`) could expose the token to root-equivalent processes. Mitigation: In the CVM threat model, all processes run within the same trust boundary; an attacker with root access has already compromised the TEE. This is acceptable for Phase A.
- **[Single token, no rotation]** → If token is leaked mid-session, no revocation mechanism exists. Mitigation: Token lifetime = VM lifetime; reboot generates a new token. For longer-lived deployments, Phase B (mTLS or socket credentials) provides the fix.
- **[Dev mode bypass]** → Misconfiguration in production could leave auth disabled. Mitigation: `start.sh` always generates and sets `TRUCON_SERVICE_TOKEN` and never sets `TRUCON_AUTH_DISABLED`. The warning log is prominent.
- **[No per-caller identity]** → Cannot restrict Docktap to write-only. Mitigation: Not needed today; event_type provides source tracing. Phase B can add granular authorization if required.
