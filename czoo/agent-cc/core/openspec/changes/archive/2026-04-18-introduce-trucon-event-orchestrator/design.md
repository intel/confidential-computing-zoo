## Context

The current trusted logging flow is embedded inside existing lifecycle handlers and relies on in-process objects. This creates scale and consistency risk once REST API runs with multiple workers and Docktap runs as an independent process. The architecture direction is to preserve the existing REST control-plane behavior, add Docktap as a dedicated process, and centralize trusted event handling into a TruCon core service that governs event ingestion, submission lifecycle, and instance mapping.

Stakeholders include API maintainers, Docktap maintainers, security/attestation owners, and operations teams responsible for reliability and observability.

## Goals / Non-Goals

**Goals:**
- Reuse existing REST API architecture for user-facing control-plane behavior.
- Support Docktap as a dedicated service process that emits trusted runtime events.
- Introduce TruCon as the single internal boundary for trusted event ingest, commit/submit lifecycle management, and instance mapping queries.
- Define deterministic and observable queue-driven submission semantics under multi-process concurrency.
- Preserve external API compatibility while evolving internal service topology.

**Non-Goals:**
- Rewriting all existing build/publish/launch business logic in one phase.
- Requiring immediate replacement of all existing trusted-log file formats.
- Defining provider-specific immutable backend details in this change.
- Introducing new public external APIs unrelated to trusted-event and mapping boundaries.

## Decisions

1. Service boundary: TruCon is a core service, not a thin writer.
- Rationale: TruCon must own event ingest, submission orchestration, and mapping semantics.
- Alternative considered: Keep a pure writer service and separate mapping service. Rejected for now due to higher integration overhead and split observability during migration.

2. Keep existing REST API as control plane.
- Rationale: Preserves current integration expectations and minimizes user-facing behavioral churn.
- Alternative considered: Move all lifecycle orchestration into TruCon immediately. Rejected because it creates unnecessary scope and migration risk.

3. Docktap runs as an independent process and reports events to TruCon.
- Rationale: Matches runtime interception responsibilities and improves process isolation.
- Alternative considered: Keep Docktap logic inside REST process. Rejected because it weakens scaling and lifecycle isolation.

4. TruCon submission model is queue-driven with explicit lifecycle states.
- Rationale: Decouples client latency from immutable backend latency and supports retries safely.
- Alternative considered: synchronous submit on commit. Rejected because backend instability would directly impact caller latency and reliability.

5. Instance mapping is first-class in TruCon.
- Rationale: Auditing and verification require correlation between workload identity, runtime instance identity, and trusted events.
- Alternative considered: infer mapping indirectly from event payload only. Rejected because query complexity and ambiguity increase over time.

## Risks / Trade-offs

- [Risk] TruCon can become a bottleneck if all writes are centralized.
  - Mitigation: use queue partitioning, idempotent writes, and horizontal scale with ownership controls.

- [Risk] Migration period may have dual paths (legacy local writes and TruCon path).
  - Mitigation: phase rollout with explicit feature flags and parity checks on critical flows.

- [Risk] Event ordering ambiguity when multiple sources emit related events concurrently.
  - Mitigation: define chain scope rules and source-aware ordering constraints in specs.

- [Risk] Operational complexity increases with an extra internal service.
  - Mitigation: establish baseline health, queue, retry, and lag metrics from day one.

## Migration Plan

1. Define and freeze TruCon API contracts for event lifecycle and mapping.
2. Integrate existing REST API trusted-event writes through TruCon boundary while preserving external API outputs.
3. Integrate Docktap process emission to TruCon and validate mapping correctness.
4. Enable queue-driven submission worker behavior with observability thresholds.
5. Gradually disable legacy direct trusted-log mutation paths after parity validation.

Rollback strategy:
- Use feature flags to route writes back to legacy local path if TruCon availability or correctness thresholds are violated.
- Preserve existing external REST responses to avoid client impact during rollback.

## Open Questions

- Should chain scope be per workload, per tenant, or global in initial rollout?
- What is the required freshness SLA from commit accepted to backend confirmed?
- Which fields are mandatory for stable instance mapping across restarts and replacements?
- Should submission worker ownership be process-local or coordinated through shared leases?
