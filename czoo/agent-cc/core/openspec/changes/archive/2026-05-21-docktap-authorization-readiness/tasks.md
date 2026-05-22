## 1. Service Policy And Readiness Surface

- [x] 1.1 Add service-side default delegation policy for TTL and scope so the common path no longer depends on caller-supplied values.
- [x] 1.2 Introduce a readiness-oriented tc-api capability that can report or ensure Docktap authorization for a target chain using service defaults.
- [x] 1.3 Shape the readiness response so callers receive a stable summary including readiness state, target chain, effective scope, and expiry.

## 2. Delegation And Docktap Integration

- [x] 2.1 Update delegation creation paths so the primary readiness flow uses service-default TTL and scope when explicit overrides are absent.
- [x] 2.2 Preserve `POST /api/docktap/delegate` as a lower-level operator/debug path while aligning its behavior and documentation with the new policy model.
- [x] 2.3 Update Docktap authorization challenge handling so readiness/preflight is the preferred recovery path while runtime challenge remains the fallback.

## 3. External Consumption Paths

- [x] 3.1 Add one primary preflight skill contract for agent consumers that wraps the readiness flow without exposing raw delegation mechanics.
- [x] 3.2 Document and/or provide the equivalent explicit preflight wrapper path for non-agent callers such as fixed scripts or launch wrappers.
- [x] 3.3 Decide whether the first version also ships an optional status/debug skill, and if included, define it as a separate non-primary integration surface.

## 4. Verification And Rollout

- [x] 4.1 Add or update tests covering readiness success, delegation reuse, delegation creation through readiness, and fallback challenge behavior.
- [x] 4.2 Add or update tests covering service-default TTL and scope application when callers omit those values.
- [x] 4.3 Update operator and integration documentation to distinguish the preferred readiness/preflight path from the retained raw delegation API path.