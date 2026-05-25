## Context

The repository now has architecture and specification-level documentation for a confidential memory control plane and an OpenViking adapter, but it does not yet have a narrow implementation slice that establishes trust before OpenClaw sends context to OpenViking. The largest unresolved risk is allowing context transfer without a concrete evidence fetch, verification step, freshness rule, and deny path.

This change intentionally targets the smallest viable boundary: verify OpenViking before `send_context`, reuse that verification result for a short period, and deny context transfer when trust cannot be established. It uses the repository's attested-head evidence and `tc-verify` compatibility model for semantics, but it does not require the full `tc-api` runtime or the full confidential-memory control-plane runtime package.

## Goals / Non-Goals

**Goals:**
- Define a first implementation slice for fail-closed context-send trust establishment.
- Require OpenViking to provide a dedicated evidence surface and a separate posture surface.
- Require OpenClaw to invoke a local verify skill before sending context.
- Define a five-minute trust-cache model so repeated sends do not require full verification on every request.
- Define allow and deny semantics for `send_context` that never degrade into partial or plaintext-fallback transfer.
- Define a minimal metadata-only decision-record contract for context-send decisions.

**Non-Goals:**
- Full gateway-wide route policy for all OpenViking operations.
- OpenViking internal hooks for privacy restore, archive materialization, memory extraction, or egress.
- Capability-lease, key-release, or broader secure-session protocols.
- A new RA-derived session-key negotiation mechanism.
- A full `cmem_control` runtime package or a requirement to run the entire `tc-api` stack as a library dependency.

## Decisions

### Decision: OpenViking provides the trust evidence

OpenViking, not an external gateway, is the primary source of evidence for context-send trust establishment.

Rationale:
- The trust gate should bind to the actual confidential memory target instead of only to an intermediate proxy.
- This keeps the first slice aligned with the stated requirement that OpenViking is the verified confidential memory service.

Alternatives considered:
- Gateway-hosted primary evidence: rejected for the first slice because it risks proving only the proxy boundary rather than the target OpenViking instance.

### Decision: Verification happens through a local OpenClaw verify skill

OpenClaw calls a local verify skill before context transfer. The skill fetches evidence, validates required claims, and returns `allow` or `deny`.

Rationale:
- This keeps the trust decision at the exact point where context would otherwise leave OpenClaw.
- It matches the existing adapter direction that the verify skill is a trust gate, not a memory client.

Alternatives considered:
- Verify inside a remote gateway only: rejected for the first slice because it weakens the local fail-closed boundary for context send.

### Decision: Use a five-minute trust cache instead of a new RA-derived session protocol

Successful verification may be reused for five minutes when the cache key still matches the expected target and policy context.

Rationale:
- The repository already uses short-lived TTL semantics and freshness windows around evidence and intents.
- A five-minute cache is materially simpler than introducing a new remote-attestation key-agreement or secure-session protocol in the first proposal.

Alternatives considered:
- Re-run full verification on every send: rejected as unnecessary for the first slice and likely too expensive operationally.
- Introduce RA-derived session keys immediately: rejected because it expands the scope from trust establishment into protocol design.

### Decision: Deny blocks context transfer outright

When verification fails, expires, mismatches expected claims, or cannot be performed, OpenClaw does not send context.

Rationale:
- The existing control-plane design requires fail-closed context transfer.
- Partial or degraded context send would silently violate the trust boundary and blur the policy contract.

Alternatives considered:
- Degraded context send with limited context: rejected because it creates ambiguous security semantics in the first slice.

### Decision: Separate evidence and posture surfaces

The change requires a dedicated evidence endpoint and a separate posture endpoint.

Rationale:
- Trust evidence and operational readiness are different contracts.
- Keeping them separate avoids overloading health or status endpoints as security assertions.

Alternatives considered:
- Reuse a single status endpoint for both trust and posture: rejected because it makes verification semantics ambiguous.

### Decision: Keep minimal decision recording in scope

The first slice records metadata-only `context_send.allow` and `context_send.deny` outcomes without requiring a full general ledger framework.

Rationale:
- The trust decision is more useful if it leaves a verifiable audit trail.
- Restricting the event set to context-send outcomes keeps the first slice small.

Alternatives considered:
- No decision record in the first slice: rejected because it weakens auditability.
- Full operation vocabulary in the first slice: rejected as too broad.

## Risks / Trade-offs

- [Short TTL still allows stale trust within the cache window] -> Bind the cache key to instance, measurement, ledger head, and policy version, and require re-verification after five minutes.
- [Evidence endpoint design may drift toward generic status] -> Require a dedicated evidence surface and a separate posture surface in the specs.
- [`tc-verify` coupling may become too concrete too early] -> Require compatibility with attested-head evidence semantics, not a hard dependency on one specific invocation path.
- [Decision recording can broaden scope] -> Keep the first event set limited to `context_send.allow` and `context_send.deny`.
- [Gateway-first deployment pressure may re-expand scope] -> State explicitly that gateway-wide policy and OpenViking internal hooks are future work.

## Migration Plan

1. Add the new capabilities and contracts in this change.
2. Implement OpenViking evidence and posture surfaces.
3. Implement the local OpenClaw verify-skill flow.
4. Add the five-minute trust cache keyed to verified target and policy context.
5. Add minimal metadata-only decision recording for context-send outcomes.
6. Defer broader gateway policy, leases, key release, and internal OpenViking hooks to later changes.

Rollback is straightforward because this change is additive at the capability level. If rollout causes issues, implementations can disable the new trust gate and fall back to the pre-change integration path while preserving the specification boundary for later iteration.

## Open Questions

- Whether the first implementation should call `tc-verify` through a CLI wrapper, a library adapter, or an internal compatibility layer.
- Whether the evidence surface should expose ledger-head material directly or only an evidence package that already embeds the required binding.
- Whether the minimal decision record should be required for every deny, or only when a ledger sink is configured and reachable.