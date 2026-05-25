# Deployment Profiles

The Confidential Memory Control Plane can be deployed in several ways. A verifier or policy gateway is useful in some profiles, but it is not the universal abstraction.

## Profile 1: Metadata-Only Policy Mode

```text
framework adapter -> control plane -> allow/deny -> framework continues
```

The adapter sends metadata-only requests before sensitive memory operations. The control plane returns decisions and records trusted decision events.

Best for:

- SDK wrappers
- host-plugin adapters
- early integration phases

Limitations:

- does not prove the memory service itself is running inside a confidential boundary
- key release and runtime evidence may be deferred

## Profile 2: Gateway-Protected Remote Memory Mode

```text
agent host -> verifier/policy gateway -> memory service
```

A gateway handles attestation checks, posture checks, policy prechecks, scoped headers, and metadata-only audit before forwarding requests to a remote memory service.

Best for:

- service-style memory frameworks
- OpenViking HTTP integration
- agentmemory REST/MCP server deployments
- mem0 server or cloud-style deployments

Constraints:

- a non-confidential gateway must not inspect or persist session plaintext
- route policy must distinguish recall, materialization, commit, and egress
- gateway failure should fail closed for context transfer and materialization

## Profile 3: Attested Memory Service Mode

```text
agent host -> local verify gate -> attested memory service
```

The memory service exposes evidence or posture claims directly. The caller verifies attested evidence before sending context or performing sensitive operations.

Best for:

- OpenViking as a confidential memory service
- service owners that can expose evidence endpoints
- deployments where OpenClaw and OpenViking are operated by different parties

Limitations:

- service internals still need hooks for privacy restore, archive materialization, memory extraction, and egress policy if complete confidentiality is required

## Profile 4: Attestation-Gated Key-Release Mode

```text
memory service evidence -> control plane -> key broker -> scoped key lease
```

Key material or key handles are released only when evidence verification and policy authorization pass.

Best for:

- encrypted memory stores
- tenant-scoped memory keys
- privacy-restore gates

Limitations:

- requires key broker design and operational policy beyond this documentation-only change
- key release should be separately logged as a high-value trusted decision event

## Profile 5: Confidential Agent Runtime Mode

```text
client -> policy gate -> attested agent runtime -> protected state core
```

The whole stateful agent runtime, or at least its memory and state core, is inside a confidential boundary.

Best for:

- Letta-like full agent runtimes
- systems where memory mutation happens inside the runtime loop

Limitations:

- ingress gateways alone do not see internal state mutations
- runtime-level hooks or confidential deployment boundaries are required

## Gateway Suitability

Gateway is suitable when:

- the framework has a stable network boundary
- policy can be decided using metadata, claims, scopes, and evidence references
- the gateway does not need plaintext inspection outside a confidential boundary
- the deployment goal is trust establishment, scoped access, and fail-closed routing

Gateway is not sufficient when:

- memory runs in-process as an SDK
- sensitive transitions happen inside an agent runtime
- raw materialization happens behind the gateway
- the gateway must read session plaintext to decide
- key release must occur inside the memory core

## Recommendation

Use the control plane as the universal abstraction. Use a gateway only where the integration shape naturally has a stable service boundary.