## Context

Docktap now holds three classes of local state during normal operation: in-memory operation routing state in `OperationTracker`, persisted container-to-workload mapping state in `WorkloadStore`, and in-process TruCon retry bookkeeping in `TruConCommitter`. The current code already exposes partial cleanup machinery for the operation tracker, but there is no single owner for cleanup, no lifecycle-aware deletion policy for workload mappings, and no retention policy for acknowledged or terminal retry records.

This change must preserve the existing trust boundary. Replay and verification depend on the chain committed through TruCon and immutable backends such as Rekor, not on Docktap-local persistence. That constraint allows Docktap-local state to be treated as bounded operational cache and short-lived diagnostics instead of long-term evidence storage.

The change also closes an obsolete migration assumption from the parent TruCon orchestration change. Legacy write-path rollback is no longer a valid operational fallback, so the remaining rollout guidance must be rewritten around TruCon-only operation, process supervision, parity checks, and degraded-mode handling.

## Goals / Non-Goals

**Goals:**
- Keep Docktap local state bounded in long-running deployments.
- Preserve routing continuity for active containers while allowing removed-container state to expire after a grace window.
- Preserve retryable TruCon submissions until they are acknowledged or terminally exhausted.
- Retain acknowledged and terminal retry records long enough for operator troubleshooting, with explicit independent TTLs.
- Use the simplest runtime ownership model possible: one Docktap-owned periodic sweeper.
- Replace obsolete legacy-fallback rollout guidance with TruCon-only runbook guidance.

**Non-Goals:**
- Changing TruCon or Rekor replay semantics.
- Making Docktap-local state part of the verification boundary.
- Introducing distributed cleanup coordination, shared leases, or external schedulers.
- Retaining local state indefinitely for audit or archival use.
- Reintroducing a legacy direct trusted-log write fallback.

## Decisions

1. Replay depends only on TruCon and immutable backend state.
- Rationale: Docktap-local state is not authoritative trust evidence, so retention and GC decisions must not be framed as verification prerequisites.
- Alternative considered: preserve local state until external confirmation or operator export. Rejected because it inflates Docktap into an evidence store and couples runtime memory growth to backend timelines.

2. Docktap uses one periodic background sweeper.
- Rationale: a fixed-interval daemon thread is simpler and more predictable than per-request cleanup or mixed trigger models, especially in low-traffic deployments where request-triggered cleanup may never run.
- Alternative considered: cleanup after every N operations. Rejected because it makes cleanup cadence traffic-dependent and complicates testing and tuning.

3. Local state is modeled as two retention layers.
- Rationale: routing and mapping state have different lifetimes from retry diagnostics. Separating them keeps TTLs understandable and prevents operator-facing retry retention from bloating core routing tables.
- Alternative considered: a single global Docktap retention TTL. Rejected because active container routing, removed-container mappings, acknowledged retries, and terminal failures need different policies.

4. `WorkloadStore` gains minimal lifecycle fields.
- Rationale: `created_at`, `last_seen_at`, `removed_at`, and `last_operation` are sufficient to express active vs terminal lifecycle state and removed-container grace periods without speculative over-modeling.
- Alternative considered: storing richer history such as operation counters or full state machines. Rejected because this change needs bounded retention, not full lifecycle analytics.

5. `rm` is the terminal lifecycle boundary for persisted workload mappings.
- Rationale: the current Docktap routing model treats one `create -> rm` lifecycle as one container instance. Before `rm`, mappings may still be needed for start/stop routing. After `rm`, only a short troubleshooting window is needed.
- Alternative considered: age-based mapping expiry regardless of lifecycle. Rejected because it risks deleting still-active mappings and breaking routing continuity.

6. Retry retention semantics are state-specific.
- Rationale: retryable submissions must never be garbage-collected while still pending, acknowledged submissions need only short-lived diagnostics, and terminal failures need a longer operator window.
- Alternative considered: treat acknowledged and terminal records identically. Rejected because it either keeps success records too long or discards failure context too quickly.

7. Configuration is explicit and per-state-class.
- Rationale: separate settings make behavior predictable and operational tuning safe.
- Recommended defaults:
  - `DOCKTAP_GC_INTERVAL_SECONDS=300`
  - `DOCKTAP_OPERATION_RETENTION_HOURS=24`
  - `DOCKTAP_REMOVED_CONTAINER_RETENTION_HOURS=24`
  - `DOCKTAP_ACKED_RETRY_RETENTION_HOURS=24`
  - `DOCKTAP_TERMINAL_RETRY_RETENTION_HOURS=168`
- Alternative considered: a single retention env var plus hard-coded exceptions. Rejected because it obscures operator intent and encourages accidental coupling between unrelated state classes.

## Risks / Trade-offs

- [Risk] A removed container mapping may be deleted before an operator expects to inspect it locally.
  - Mitigation: keep a removed-container grace window and document that authoritative replay and audit come from TruCon and immutable backends, not Docktap-local state.

- [Risk] Aggressive cleanup could remove acknowledged retry records before short-term troubleshooting completes.
  - Mitigation: retain acknowledged and terminal retry records under separate TTLs and expose the settings as explicit environment variables.

- [Risk] Future routing behavior may need more lifecycle metadata than the minimal field set.
  - Mitigation: keep the schema minimal now and extend only if a new routing requirement appears; this design does not block additive fields later.

- [Risk] Another background thread increases Docktap runtime complexity.
  - Mitigation: keep ownership local to Docktap, use a simple periodic loop, and reuse existing in-process lifecycle patterns.

## Migration Plan

1. Add the retention configuration surface and periodic sweeper ownership to Docktap startup.
2. Extend `WorkloadStore` schema and update lifecycle-touch paths so active and removed mappings are distinguishable.
3. Teach the sweeper to clean `OperationTracker`, removed-container mappings, and expired acknowledged or terminal retry records.
4. Add focused tests for lifecycle-aware mapping cleanup and retry-state retention boundaries.
5. Update operational documentation and the remaining parent-change runbook item to describe TruCon-only rollout, degraded-mode handling, and process supervision without legacy fallback.

Rollback strategy:
- If retention behavior causes routing regressions, operators can disable or relax cleanup via the new environment variables while keeping TruCon as the sole trust-event path.
- There is no rollback to a legacy direct write path; rollback means reducing GC aggressiveness, not bypassing TruCon.

## Open Questions

- None blocking proposal readiness. Default TTL values may still be tuned during implementation, but the ownership model, lifecycle boundary, and verification assumptions are settled.