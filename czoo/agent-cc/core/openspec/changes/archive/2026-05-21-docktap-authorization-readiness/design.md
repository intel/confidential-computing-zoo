## Context

Docktap explicit delegation already provides the cryptographic authorization model for reusing one OIDC-backed login across later Docker runtime operations, but the primary caller experience is still low-level. Agent-style integrations encounter authorization only when the runtime blocks, while fixed-script or wrapper-based integrations are pushed toward raw delegation creation instead of a stable readiness surface.

This change keeps the existing delegation model and Docktap enforcement path, but moves default policy control into tc-api/Docktap and adds a higher-level authorization-readiness capability that can be consumed non-invasively. The design must support both agent consumers (through skills/workflows) and non-agent consumers (through explicit preflight/wrappers) without requiring OpenClaw or Hermes lifecycle changes.

## Goals / Non-Goals

**Goals:**
- Provide one service-side authorization readiness flow that callers can use before Docker-backed work starts.
- Move default delegation TTL and default delegation scope under tc-api/Docktap policy instead of agent-estimated task duration.
- Preserve the existing delegation event model, verification chain, and Docktap runtime enforcement semantics.
- Keep raw delegation creation available for operator/debug use while making it secondary to the readiness flow.
- Support both agent and non-agent callers through the same service capability with different outer wrappers (skill vs. explicit preflight wrapper).

**Non-Goals:**
- Modifying OpenClaw or Hermes core lifecycle code.
- Introducing multi-user or multi-identity delegation isolation on a shared chain.
- Turning readiness into a full Docker daemon or registry health check.
- Adding task-duration estimation or task-specific TTL calculation.
- Removing the existing Docktap challenge fallback path.

## Decisions

### Decision: Treat authorization readiness as the top-level integration boundary
The new caller-facing surface will represent "Docktap authorization ready" rather than exposing delegation creation as the main concept.

Rationale: This matches how integrations actually need to consume the feature. Agent skills and wrappers need a stable answer to "can I safely start Docker-backed work now?" rather than a low-level delegation primitive.

Alternative considered: Expose only the raw delegation create API and ask skills/wrappers to compose readiness themselves. Rejected because it leaks delegation mechanics back into every integration and preserves the current brittle user path.

### Decision: Service-side policy provides default TTL and scope
Default TTL and default scope will come from tc-api/Docktap policy. Callers using the main readiness flow will not estimate task duration or select scope as part of the common path.

Rationale: Agent-side TTL estimation is unreliable, and requiring callers to choose scope/TTL keeps too much policy logic outside the service boundary. Centralizing defaults makes the preflight path simpler and more repeatable.

Alternative considered: Require each caller to choose TTL and scope. Rejected because it increases caller complexity and makes preflight hard to standardize across agent and non-agent entry points.

### Decision: Keep raw delegation creation as a lower-level/operator path
`POST /api/docktap/delegate` remains available, but it is no longer the preferred top-level integration story.

Rationale: Existing tests, operator workflows, and debugging paths benefit from retaining a direct creation primitive. Preserving it also reduces migration risk.

Alternative considered: Replace the raw endpoint entirely with readiness-only semantics. Rejected because it would remove a useful low-level control surface and unnecessarily complicate debugging and backward compatibility.

### Decision: Use one core readiness capability for both agent and non-agent callers
The service layer will expose one readiness-oriented capability. Agent integrations can wrap it with a preflight skill; non-agent integrations can wrap it with explicit preflight commands or launch wrappers.

Rationale: The policy and readiness contract should stay uniform even when the outer UX differs.

Alternative considered: Separate agent-only and non-agent-only service flows. Rejected because it duplicates semantics and makes behavior drift likely.

### Decision: Preserve Docktap runtime challenge as fallback, not primary UX
Readiness/preflight becomes the preferred entry path, but runtime challenge remains in place when callers skip preflight or arrive through older paths.

Rationale: This maintains safety and backward compatibility. It also gives a recovery path for integrations that fail to preflight correctly.

Alternative considered: Disable challenge once readiness exists. Rejected because it would weaken enforcement and make missing-preflight failures harder to recover from.

## Risks / Trade-offs

- [Broader authorization window than task-specific TTL] -> Mitigation: keep TTL configurable at the service policy layer and document that this change intentionally favors stable preflight over per-task estimation.
- [Default scope may be broader than a single task needs] -> Mitigation: keep default scope explicit in policy and leave fine-grained scope derivation as future work rather than hiding it.
- [Callers may still bypass readiness and keep using the raw delegation endpoint] -> Mitigation: document readiness as the preferred contract and position raw delegation as operator/debug level behavior.
- [A readiness surface can be mistaken for full Docker health] -> Mitigation: specify clearly that readiness covers authorization only, not daemon, registry, or workload correctness.
- [Single-user-per-chain assumption may be insufficient later] -> Mitigation: keep this assumption explicit in the design and proposal, and exclude multi-identity chain sharing from this change.

## Migration Plan

1. Add service-side policy defaults for delegation TTL and delegation scope.
2. Add a readiness-oriented tc-api capability that can report or ensure Docktap authorization under those defaults.
3. Retain the raw delegation create path, but update documentation and integrations to prefer readiness/preflight.
4. Add one primary preflight skill for agent consumers and document wrapper/preflight usage for non-agent callers.
5. Keep Docktap challenge behavior as fallback during and after rollout.

## Open Questions

- Should the first readiness surface be a single idempotent ensure operation, or should tc-api also expose a separate status-only API from the start?
- Should the optional debugging/status skill ship in the same change as the main preflight skill, or remain a follow-up if the main path is sufficient?
- Should policy defaults stay global for the first version, or should the design leave a concrete extension point for per-chain policy without implementing it now?