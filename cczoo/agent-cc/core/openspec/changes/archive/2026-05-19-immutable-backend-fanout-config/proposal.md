## Why

TruCon currently selects exactly one immutable-log backend at startup, which blocks any staged rollout where Rekor remains the authoritative path while an on-chain backend is introduced in parallel. The system needs an explicit configuration model for single-backend and multi-backend wiring now so the code can grow toward dual recording without forcing an incomplete on-chain adapter into production use.

## What Changes

- Add configuration for immutable backend selection as a set of enabled write backends rather than a single backend string.
- Add a composite immutable-log adapter skeleton that can fan out submissions to multiple backend adapters while preserving one configured read/primary backend.
- Define startup validation rules so `rekor,onchain` cannot be enabled while the on-chain adapter is still a placeholder.
- Preserve existing single-backend behavior for `rekor`-only and `onchain`-only startup modes.
- Establish write-policy semantics for future multi-backend confirmation without requiring immediate backend-status schema expansion in this change.

## Capabilities

### New Capabilities
- `immutable-backend-fanout`: Configure TruCon to wire immutable-log backends as a fanout-capable set with an explicit primary/read backend and guarded startup rules for unsupported combinations.

### Modified Capabilities
- `backend-adapter-isolation`: Change runtime backend loading requirements from single-value backend selection to validated multi-backend configuration while keeping backend adapters as independent packages.

## Impact

- Affected code: `tc_api/trucon/config.py`, `tc_api/trucon/app.py`, `tc_api/trucon/submit_daemon.py`, and a new composite immutable adapter module under `tc_api/trucon/`.
- Affected specs: immutable backend adapter loading and configuration requirements, plus new fanout configuration behavior.
- Operator impact: startup configuration changes from one backend selector to backend-set configuration with validation errors for unsupported multi-backend combinations.
- Non-goal: implementing real on-chain submission, replay, or verification semantics in this change.