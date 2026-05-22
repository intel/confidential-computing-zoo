## Why

The current internal TruCon trust boundary is still based on HTTP plus a shared Bearer token, which is acceptable for the repository's current working state but too weak and too coarse for the intended same-machine deployment model. The project has now explicitly decided that tc_api, Docktap, and TruCon remain same-machine components, so the next change should harden that local boundary around Unix socket transport, peer-credential-based caller identity, and minimal caller policy instead of carrying forward a generic cross-node auth design.

## What Changes

- Add a Unix-domain-socket internal control-plane transport for TruCon so tc_api and Docktap no longer rely on long-lived localhost/container-network HTTP as the steady-state internal path.
- Add peer-credential-based internal caller authentication and derive a stable caller identity that distinguishes at least tc_api and Docktap.
- Add a minimal caller policy matrix so tc_api retains full internal access while Docktap remains a commit-oriented caller by default.
- Define migration expectations for the current HTTP + Bearer-token path as transitional compatibility only, not the long-term same-machine design.
- Absorb low-priority contract cleanup that this refactor naturally touches: remove or justify the unused `SubmitResult` surface and the dead `SubmitStatus.OPEN` lifecycle value.

## Capabilities

### New Capabilities
- `trucon-internal-transport`: Shared same-machine Unix socket transport for internal TruCon caller traffic, including deployment and compatibility expectations.

### Modified Capabilities
- `service-auth`: Extend service-to-service authentication from Phase A shared Bearer-token validation to Phase B peer-credential caller identity and minimal caller authorization.

## Impact

- Affected code: `src/tc_api/trucon/app.py`, `src/tc_api/tlog_client.py`, `docktap/trucon_client.py`, startup/deployment wiring, and related tests.
- Affected systems: bare-metal `start.sh`, Docker Compose service wiring, internal caller admission policy, and TruCon audit logging.
- Affected contracts: internal transport/auth behavior and touched local status/type contracts (`SubmitResult`, `SubmitStatus.OPEN`).