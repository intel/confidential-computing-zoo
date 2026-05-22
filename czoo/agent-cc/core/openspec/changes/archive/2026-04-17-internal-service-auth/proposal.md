## Why

tc_api → TruCon and Docktap → TruCon calls are currently unauthenticated HTTP on localhost. Architecture §9 requires "Internal service calls must be authenticated and authorized" and defines TruCon as the policy boundary for trusted event admission. Without authentication, any process on the CVM that can reach localhost:8001 can inject forged events into the trust chain, undermining the entire trust model.

## What Changes

- Add Bearer token authentication to all TruCon HTTP endpoints (`POST /commit`, `GET /chain-state/{chain_id}`, `GET /status`, `GET /state`, `GET /verify-chain/{chain_id}`).
- tc_api and Docktap attach `Authorization: Bearer <token>` header when calling TruCon.
- Unauthenticated requests are rejected with `401 Unauthorized` and a descriptive error body.
- A shared `TRUCON_SERVICE_TOKEN` environment variable is the single credential for both tc_api and Docktap.
- Token is generated at CVM startup by `start.sh` / `trust_service.sh` and inherited by all service processes.
- A development-mode bypass (`TRUCON_AUTH_DISABLED=true`) skips authentication for local dev and test environments, with a prominent startup warning.

## Capabilities

### New Capabilities
- `service-auth`: Bearer token authentication for TruCon internal service endpoints, including token validation middleware, development-mode bypass, and client credential attachment.

### Modified Capabilities

(none — no existing spec-level behavior changes; this adds a new cross-cutting security layer)

## Impact

- **Code**: `src/tc_api/trucon/app.py` (middleware), `src/tc_api/tlog_client.py` (header attachment), `docktap/trucon_client.py` (header attachment), `src/tc_api/config.py` (new env vars).
- **Scripts**: `start.sh` and/or `scripts/trust_service.sh` (token generation + export).
- **Tests**: All test files that exercise TruCon endpoints need either `TRUCON_AUTH_DISABLED=true` or a test token fixture.
- **APIs**: All TruCon endpoints gain a mandatory `Authorization` header requirement (except in dev mode).
- **Dependencies**: None — uses stdlib only (`secrets`, `hmac.compare_digest`).
- **Future upgrade path**: Phase A (Bearer token) documented here. Phase B (Unix socket peer credentials or mTLS) deferred to a separate change when cross-node deployment is needed. This deferral should be recorded in `overview_tasks.md`.
