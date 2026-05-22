## Why

Docktap is now a long-running service with in-memory routing state, persisted workload-mapping state, and local TruCon retry bookkeeping, but none of those local state classes have a complete retention policy. In long-lived deployments that means stale state can grow without improving replay or verification guarantees, because replay depends on TruCon and immutable backends rather than Docktap-local persistence.

## What Changes

- Add lifecycle-aware garbage collection for Docktap local state, covering in-memory operation tracking, persisted container-to-workload mappings, and local TruCon retry bookkeeping.
- Define a simple Docktap-owned periodic sweeper model instead of ad hoc or traffic-triggered cleanup.
- Add explicit retention configuration for routing state, removed-container mapping grace periods, acknowledged retry records, and terminal retry records.
- Preserve replay and verification semantics by treating Docktap local state as operational cache and short-lived diagnostics only.
- Close the obsolete parent-change rollback task by replacing legacy-fallback guidance with TruCon-only rollout and degraded-mode runbook guidance.

## Capabilities

### New Capabilities
- `docktap-local-state-retention`: defines bounded retention and garbage collection rules for Docktap-local routing, mapping, and retry state without affecting trust-chain replayability.

### Modified Capabilities
- `docktap-trucon-commit`: extends Docktap local submission behavior to include retention and cleanup rules for acknowledged and terminal retry bookkeeping.

## Impact

- Affected code: `docktap/main.py`, `docktap/proxy/operation_log.py`, `docktap/workload_store.py`, `docktap/trucon_client.py`, Docktap tests, and operational documentation.
- Affected systems: Docktap runtime lifecycle, local routing continuity, local operator diagnostics, and rollout/degraded-mode guidance for TruCon-only operation.
- No external API contract changes are expected; this change is focused on internal runtime behavior, retention controls, and operator-facing documentation.