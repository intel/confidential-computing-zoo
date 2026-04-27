## Why

Docktap is currently Docker-first in its socket naming, lifecycle classification, and runtime event contract, which makes future Podman support harder than it needs to be. We need a small but durable architectural shift now so multi-engine support can be added later without fragmenting the event schema, verifier behavior, or operator mental model.

## What Changes

- Introduce a Docktap runtime-engine abstraction that normalizes engine-specific request handling into one canonical lifecycle model for `pull`, `create`, `start`, `stop`, and `rm`.
- Require Docktap runtime commits to emit a mandatory `runtime_engine` field on all auditable runtime events.
- Keep a single `docktap-runtime` verification profile and extend it with simple engine-aware evaluation rules rather than creating a separate profile per engine.
- Define verifier behavior for `runtime_engine` values so missing values fail the runtime profile, while unknown-but-present values are treated as incomplete evaluation rather than semantic failure.
- Preserve current Docker behavior and event semantics as the baseline path while creating a clean seam for future Podman support.

## Capabilities

### New Capabilities
- `docktap-runtime-engine-abstraction`: Defines the canonical runtime-engine boundary, normalized lifecycle mapping, and engine metadata contract needed to support Docker today and Podman in the future.

### Modified Capabilities
- `docktap-trucon-commit`: Runtime commit requirements change to include mandatory `runtime_engine` metadata while preserving existing lifecycle commit semantics.
- `verification-profiles`: The `docktap-runtime` profile requirements change to evaluate `runtime_engine`, keep one mixed-engine profile, and distinguish missing versus unknown engine values.

## Impact

- Affected code: `docktap/main.py`, `docktap/proxy/docker_proxy.py`, `docktap/proxy/operation_log.py`, `docktap/trucon_client.py`, `src/tc_api/verification_profiles.py`
- Affected docs/specs: Docktap architecture and API docs, trusted-log verification docs, OpenSpec capability specs for runtime commits and verification profiles
- Affected tests: Docktap lifecycle classification tests, TruCon commit tests, runtime verification profile tests
- Dependencies/systems: Docktap runtime event schema, verifier output semantics, future Podman integration path
