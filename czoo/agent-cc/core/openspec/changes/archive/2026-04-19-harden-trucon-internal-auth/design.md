## Context

TruCon currently authenticates internal callers with a shared Bearer token over HTTP. That model was a pragmatic Phase A solution, but it leaves the same-machine trust boundary too broad: every authenticated caller looks equivalent, caller identity is not derived from the operating system, and the long-term design is still anchored on localhost or container-network HTTP.

The repository has now explicitly decided that tc_api, Docktap, and TruCon remain same-machine components. That decision changes the right optimization target. Instead of designing for cross-node transport, Phase B should harden the local control plane around a shared Unix domain socket, Linux peer credentials, and a minimal caller policy that separates tc_api from Docktap.

This change is cross-cutting. It touches TruCon admission, client libraries, deployment wiring in bare-metal and Compose modes, and the low-priority cleanup items that naturally surface when the internal control-plane contract is revisited.

## Goals / Non-Goals

**Goals:**
- make Unix domain socket transport the steady-state internal path for tc_api and Docktap
- authenticate same-machine callers using Linux peer credentials rather than only a shared secret
- derive a stable internal caller identity that distinguishes at least `tc_api` and `docktap`
- enforce a small authorization matrix at the TruCon boundary
- document the current HTTP + Bearer-token path as transitional compatibility only
- absorb `SubmitResult` and `SubmitStatus.OPEN` cleanup if the refactor touches those contracts

**Non-Goals:**
- cross-node or multi-tenant transport design
- mTLS, certificate issuance, or token rotation
- exposing OS-level peer identity in DSSE predicates or exported attested evidence
- expanding Docktap into a full TruCon administration client
- platform-specific hardening for systemd, Kubernetes, or remote verifier environments

## Decisions

### 1. Same-machine Phase B uses Unix domain sockets, not mTLS

**Choice:** internal TruCon traffic moves to a shared Unix socket path and uses peer credentials for authentication.

**Why:** the deployment assumption is now explicitly same-machine only. Unix sockets match that topology, reduce internal network exposure, and let TruCon observe caller identity through the operating system. mTLS would add certificate lifecycle complexity for a problem that is local, not network-distributed.

**Alternatives considered:**
- **mTLS**: stronger for cross-node links, but mismatched to the repository's same-machine constraint and heavier to deploy and test.
- **keep HTTP + shared token**: lowest change cost, but preserves the weakest part of the current boundary and still cannot distinguish internal callers.

### 2. Caller identity is an internal admission and audit concept

**Choice:** TruCon derives `caller_service` from the same-machine transport context and records enough peer metadata for diagnostics. The minimum required distinction is `tc_api` versus `docktap`.

**Why:** the primary value of Phase B is not just replacing one credential with another, but making internal callers distinguishable so policy and audit can reason about them. That identity belongs to local admission and observability; it should not become part of the external verification contract.

**Alternatives considered:**
- **no caller identity, auth only**: simpler, but leaves all authenticated callers equivalent and gives up the main architectural gain of the refactor.
- **embed caller identity into DSSE or exported evidence**: overreaches the problem. Peer credentials describe local process identity, not a stable external verification fact.

### 3. Minimal caller policy ships with Phase B

**Choice:** tc_api retains full internal access, while Docktap is restricted to commit-oriented operations by default.

**Why:** the current same-machine caller set is small and role-shaped. A minimal matrix gets immediate risk reduction without introducing a general-purpose RBAC system.

**Alternatives considered:**
- **allow all authenticated callers full access**: wastes the newly derived caller identity and keeps Docktap over-privileged.
- **full role-based authorization**: too much machinery for two internal services.

### 4. HTTP + Bearer-token support is compatibility-only during migration

**Choice:** the design allows a short transitional period where existing HTTP + Bearer-token wiring continues to function, but the target state is UDS-first internal transport.

**Why:** this keeps rollout and rollback manageable across bare-metal and Compose wiring, while still making the final direction unambiguous.

**Alternatives considered:**
- **immediate UDS-only cutover**: cleanest steady state, but higher migration risk because startup scripts, Compose wiring, health assumptions, and tests all move at once.
- **indefinite dual-stack support**: reduces immediate change pressure but weakens architectural clarity and invites permanent fallback behavior.

### 5. Cleanup work can ride with the refactor

**Choice:** `SubmitResult` and `SubmitStatus.OPEN` are handled as part of this change if the touched contracts make their deadness obvious.

**Why:** both are currently unresolved low-priority cleanup items. This refactor already reopens internal control-plane and contract surfaces, so it is the right time to remove dead shape rather than preserve it for inertia.

**Alternatives considered:**
- **leave cleanup for later**: smaller scope, but carries dead API surface forward into the new design.

## Risks / Trade-offs

- **[Socket-path wiring changes both bare-metal and Compose]** → migration touches startup scripts, mounts, and tests. Mitigation: keep a short compatibility window and document the target socket layout explicitly.
- **[Caller identity mapping can become deployment-coupled]** → if identity is inferred indirectly, it may drift from real runtime topology. Mitigation: define one explicit same-machine mapping model and test it in both bare-metal and Compose paths.
- **[Transitional compatibility may linger too long]** → HTTP + Bearer-token fallback can become accidental permanent behavior. Mitigation: mark it compatibility-only in specs and tasks, and include explicit removal or deprecation work.
- **[Policy too strict can block legitimate Docktap recovery paths]** → over-restricting Docktap may break future self-diagnostics. Mitigation: keep the initial matrix minimal and only expand when concrete use cases appear.

## Migration Plan

1. Introduce the shared Unix socket transport path and caller-identity admission model in TruCon.
2. Update tc_api and Docktap clients to prefer the Unix socket transport.
3. Update bare-metal and Compose deployment wiring to share the socket directory.
4. Retain HTTP + Bearer-token compatibility only as needed to complete rollout and rollback.
5. Remove or deprecate the legacy path once both internal callers and tests are stable on UDS-first behavior.
6. Resolve touched dead contracts (`SubmitResult`, `SubmitStatus.OPEN`) before considering the change complete.

## Open Questions

- Should the compatibility HTTP path be removed in the same implementation change, or explicitly deprecated and removed in a follow-up?
- What is the cleanest stable mapping from peer credentials to `caller_service` in Docker Compose without turning the policy model into container-runtime trivia?