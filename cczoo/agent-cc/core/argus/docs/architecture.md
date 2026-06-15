# Argus Architecture

## Overview

Argus is an application-non-invasive runtime trust verification framework for agent-to-service (A2S) communication in confidential computing environments.

Before an agent sends sensitive data, credentials, prompts, memory records, or intermediate results to a peer service, Argus lets the caller verify that the peer is running in an expected trusted execution environment and satisfies caller-side policy.

Argus is application-non-invasive by default:

- Evidence generation is provided through a sidecar or infrastructure integration.
- Existing communication paths can be protected through direct evidence endpoints, Envoy/Nginx evidence routing, or SPIRE-based workload identity.
- The caller keeps control of the final allow or deny decision.

Current scope note:

- This document specifies the A2S path only.
- Service-to-service triggering and cache semantics are intentionally excluded from the v1 baseline.

Argus is not automatically platform-non-invasive. Profiles that require cgroup, namespace, socket inode, process start-time, container runtime, or node-level observations may need elevated sidecar permissions, shared namespaces, or a node-scoped runtime collector.

## Problem And Goals

In a confidential computing deployment, a single trusted component is not enough to guarantee an end-to-end trusted data path. An agent may run inside a TEE while the peer service it calls remains unverified.

Without Argus, prompts, credentials, memory records, tokens, and intermediate results may be sent to peer services whose runtime state, TCB level, workload identity, or measurements are unverified.

Design goals:

| Goal | Description |
|------|-------------|
| Application-non-invasive deployment | Add trust verification without modifying business logic while making platform privilege requirements explicit in the deployment profile |
| Pluggable infrastructure | Support direct evidence endpoints, Envoy/Nginx routing, and SPIRE workload identity integration |
| Verifier independence | Work with Trustee, Attestation Service, SPIRE Server, or other verifier APIs through adapters |
| A2S-first verification | Optimize the first protocol and implementation draft for agent-to-service checks before expanding to other caller shapes |

## Trust And Threat Model

Argus exists to stop a caller from sending sensitive data to a peer whose runtime identity, TEE state, or local operating posture cannot be validated at call time.

### Threat Model Matrix

| Protected Asset | Threat | Trust Assumption | Argus Mitigation |
|-----------------|--------|------------------|------------------|
| Prompts, credentials, tokens, memory records, and intermediate results before they cross a service boundary | A remote service claims to be the expected target but runs with unexpected code, measurements, or identity | The verifier can validate quote material, TCB state, measurements, and bound report data | Require quote-backed peer evidence, verifier normalization, caller-local policy checks, and fail-closed allow or deny decisions |
| Freshness of the caller's trust decision | A replay attacker returns stale evidence from a previous request | The caller controls nonce generation and enforces bounded evidence age | Bind request context into report data, verify nonce binding, and reject stale evidence |
| Correct interpretation of service posture and identity metadata | A service exposes posture or identity metadata over a public API without binding that metadata to attested runtime state | The Evidence Provider is trusted only as a local evidence producer for the runtime instance it can observe and bind | Treat remote self-description as untrusted and elevate local posture only after evidence binding or verifier normalization |
| Correct binding between the sidecar and the intended local service instance | A compromised pod, host, or sibling workload feeds fake metadata into the sidecar while still presenting valid TEE evidence | Local observation is not trusted by itself | Require multi-source corroboration, quote-bound binding claims, and fail-closed rejection on disagreement |
| Correct target scoping in context, memory, and gateway deployments | A confused deployment treats an internal plugin or in-process extension as an independently attested peer | Same-process extensions remain part of the host runtime trust boundary | Scope Argus to remote or separable peer boundaries only |
| Caller-side policy outcome | A malformed integration bypasses policy intent by trusting incomplete local metadata or ambiguous runtime bindings | The caller is responsible for fail-closed behavior | Evaluate explicit policy over normalized claims and reject incomplete or ambiguous inputs |

### Protection Boundary Summary

| Runtime Shape | In Argus authentication protection scope? | Reason |
|---------------|-------------------------------------------|--------|
| Remote peer service | Yes | Canonical A2S target with an independent peer boundary |
| Same-host separate process | Yes | Separable local peer boundary when the process can be bound to its own runtime identity |
| Same-pod / same-VM sidecar service | Yes | Preferred local deployment shape for peer evidence production |
| In-process extension / plugin / skill | No | Internal implementation boundary of the host runtime |

### Context / Memory Service Threat Posture

For context, memory, retrieval, and similar stateful HTTP services, the preferred deployment is service plus Argus sidecar in the same pod or VM. This keeps the evidence path local, avoids changing the service's public API contract, and still lets Argus observe enough runtime facts to bind evidence to the intended service instance.

| Deployment Shape | Compatible with Argus threat model? | Notes |
|------------------|-------------------------------------|-------|
| Service + Argus in same process | Partially | Acceptable only when this is still a separable service packaged into one runtime for implementation convenience |
| Service + Argus sidecar in same pod / VM | Yes | Preferred deployment shape |
| Argus calling a remote service HTTP API to ask who it is | No | Turns application JSON into an untrusted trust source |

### Binding Closure And Assurance

Argus must not treat local binding as a deployment convention outside the trust chain. Policy-relevant local claims become trustworthy only through:

1. Quote-bound binding claims.
2. Attested identity issuance.
3. Verifier-normalized claims.

Binding assurance levels:

| Level | Meaning | Minimum Requirements | Policy Use |
|-------|---------|----------------------|------------|
| L0 | Local metadata collected but not corroborated or cryptographically bound | One local source may be present | Diagnostics only |
| L1 | Corroborated local binding | At least two independent local observations agree | Audit and rollout only |
| L2 | Quote-bound binding | L1 plus canonical binding claims included in quote report data | Minimum level for production authorization |
| L3 | Attested identity binding | L2 or attested identity issuance tied to attestation | Strongest mode for identity-centric authorization |

Field-level minimums:

| Field Class | Minimum Level | Notes |
|-------------|---------------|-------|
| Stable service identity | L2 | Must be quote-bound or verifier-normalized |
| Runtime instance identity | L2 | Must be anchored to the observed live instance |
| Dynamic posture | L2 | Must satisfy freshness requirements for the same request |
| Attested identity artifact | L3 when used as primary authorization identity | Artifact presence alone is insufficient |

### Attested Claims And Independently Verified Facts

Argus distinguishes between two different statements that are easy to confuse if they are both carried next to a valid quote.

An attested self-assertion means the workload produced a value inside the attested flow and the caller can verify that this exact workload instance said it during this request. This is stronger than unauthenticated application JSON, but it still does not automatically mean the value is independently true in the deployment domain.

An independently verified identity fact means the value is not only carried through attested evidence, but also anchored by an authority or verification path outside the workload's own self-description. Typical examples are:

1. a workload identity accepted only after verifier-validated attested issuance,
2. an image or launch identity accepted only after measurement-to-reference-value verification, or
3. an endpoint or instance join accepted only after the profile's continuity and endpoint-binding predicates succeed.

This distinction matters because quote binding proves integrity of the statement, not universal truth of the statement. A service can still attest to a wrong `service_name`, `service_id`, `image_digest`, `launch_digest`, or `spiffe_id` if those values come only from its own local view. Argus therefore treats such values as policy-authoritative only when they reach the minimum assurance required by the profile through quote binding, verifier normalization, attested issuance, reference-value matching, or another explicitly governed external authority.

Operationally:

1. quote-bound self-assertions may establish that a specific TEE instance made a claim for this caller request,
2. verifier-normalized or externally anchored claims may establish that the claim is acceptable as an authorization identity, and
3. any field that remains only local, unsupported, or diagnostic must not become the sole policy anchor.

### Expected Service Verification Path

Argus should treat proof of the expected remote service as a composed verification path, not as a single field match. In the common path, the caller checks that:

1. the returned evidence is bound to this request and this target context,
2. the quote and TCB are valid,
3. measurements or attested identity material match governed expectations for the intended service, and
4. the verified live instance still joins back to the endpoint the caller is about to use.

This path is designed to detect tampering that changes measured code, launch state, attested issuance, reference-value resolution, or endpoint-to-instance continuity. It is not designed to prove that every quote-bound self-description is independently true without an external anchor, and it cannot by itself detect compromises that preserve accepted measurements and identity anchors while changing higher-level runtime behavior.

### Instance Continuity And Endpoint Binding

Each deployment profile must define:

- A minimum anchor evidence set.
- A continuity predicate.
- An endpoint-binding predicate.
- Accepted corroboration independence dimensions.

Minimum continuity expectations:

| Deployment Profile | Continuity Predicate For L2 |
|--------------------|-----------------------------|
| Kubernetes sidecar | Process identity, process start time, pod UID, container identity, and cgroup or namespace membership refer to the same live workload instance at collection and re-check time |
| VM service | VM instance identifier, process identity, process start time, launch or image digest, and bound local endpoint remain consistent across collection and re-check |
| Bare process | Process identity, process start time, executable digest, and bound local endpoint remain consistent across collection and re-check |

Minimum endpoint-binding rules:

1. A listener must join back to the active continuity predicate.
2. Proxy or service mesh interception must be documented in the profile.
3. UDS path strings alone are insufficient without current ownership or peer identity.
4. Endpoint observations outside the continuity predicate are diagnostic only.

## System Architecture

Argus is organized around three responsibilities:

| Role | Component | Responsibility |
|------|-----------|----------------|
| Caller-side trust gate | Argus Guard | Orchestrates evidence retrieval, verifier calls, policy evaluation, and allow or deny decisions |
| Service-side evidence producer | Argus Evidence Provider | Produces nonce-bound TEE evidence and runtime claims for the local workload |
| External trust service | Trustee / Attestation Service / SPIRE Server | Validates quote, TCB, measurements, nonce binding, and identity claims, or issues attested workload identity |

### End-To-End Verification Flow

The baseline Argus decision path is:

1. The caller-side Guard inside the agent runtime identifies a target service and the local policy that applies to that call.
2. The Guard generates a fresh nonce and sends an evidence request to the peer's Evidence Provider.
3. The Evidence Provider gathers local runtime facts through the Service Runtime Binding layer and asks the platform attestation stack to produce quote material.
4. The Evidence Provider returns nonce-bound evidence plus selected binding claims.
5. The Guard sends the returned evidence to the configured verifier adapter.
6. The verifier validates quote material, report-data binding, TCB state, measurements, and any attested identity material, then normalizes the result into verifier claims.
7. The Guard evaluates caller-local policy over verifier-normalized claims, profile constraints, and any allowed binding claims.
8. The Guard returns `ALLOW` or `DENY` before the sensitive business call proceeds.

This split is deliberate: service-side components produce evidence, verifier-side components validate it, and the caller remains the final authorization point.

## Evidence Binding Model

### Evidence Binding Terms

| Term | Meaning |
|------|---------|
| Nonce binding | Proof that returned evidence was generated for the caller's fresh challenge and target context |
| Canonical encoding | Deterministic byte representation of fields bound into evidence |
| Domain separation | Fixed prefix preventing Argus evidence hashes from being confused with another protocol |
| Binding closure | Requirement that any policy-relevant binding claim must be verifier-normalized or quote-bound |

### Canonicalization Rules

This section exists only to guarantee that the caller, service, and verifier hash the same bytes. It is not a separate feature.

Field-specific normalization constraints for `service_name`, `service_id`, `instance_id`, `image_digest`, `launch_digest`, `spiffe_id`, `policy_version`, and posture enums are documented on the corresponding Rust API fields in [API Contract](./api.md).

Only these generic rules matter here:

1. JSON objects use sorted keys, UTF-8, and no insignificant whitespace.
2. Missing fields and explicit `null` are not equivalent.
3. Field values must already be normalized before hashing.
4. Cross-implementation tests must use shared golden vectors.

### Binding Procedure

The goal of binding is simple: the service must prove that the quote it returns was produced for this caller request, not for some earlier or different request.

Define the three binding inputs as:

1. `domain`: a fixed Argus protocol prefix, `"argus-evidence-v1" || 0x00`.
2. `canonical_request`: the canonical byte encoding of the exact `EvidenceRequest` the service received.
3. `canonical_binding_claims`: the canonical byte encoding of the exact `BindingClaims` the service will return next to the quote.

More explicitly:

$$
canonical\_request = Canon(EvidenceRequest)
$$

$$
canonical\_binding\_claims = Canon(BindingClaims)
$$

$$
domain = "argus-evidence-v1" \parallel 0x00
$$

Where `Canon(...)` means canonical JSON with sorted keys, UTF-8 encoding, no insignificant whitespace, and field values already normalized according to the rules above.

Operationally, the flow is:

1. The caller builds `EvidenceRequest`, including a fresh `nonce`.
2. The service computes `canonical_request = Canon(EvidenceRequest_received)`.
3. The service computes `canonical_binding_claims = Canon(BindingClaims_to_be_returned)`.
4. The service computes:

$$
report\_data = SHA384(domain \parallel canonical\_request \parallel canonical\_binding\_claims)
$$

5. That digest is placed into the TEE quote's `report_data` field.
6. The service returns the quote, the emitted `binding_claims`, and `nonce_binding` metadata.
7. The verifier recomputes the expected digest and checks that it matches the quote `report_data`.

These three inputs are bound into `report_data` for different reasons:

1. `domain` gives domain separation. Without it, the same byte concatenation might be misinterpreted as belonging to another protocol.
2. `canonical_request` binds the quote to this caller challenge and target context, especially the `nonce`, `caller_id`, profile, and target fields.
3. `canonical_binding_claims` binds the quote to the exact local identity and posture claims returned in the response, so the service cannot return one quote and a different unbound claim set.

`report_data` is the right place for this binding because it is the caller-chosen data field that becomes covered by the attestation quote. Once the verifier confirms that the quote is valid and that its `report_data` matches the recomputed digest, the caller gains one attested statement tying together:

1. the fresh request it sent,
2. the binding claims returned by the service, and
3. the TEE instance that produced the quote.

The v1 binding formula is:

```text
binding_algorithm = "argus-evidence-v1-sha384"
canonical_request = Canon(EvidenceRequest)
canonical_binding_claims = Canon(BindingClaims)
domain = "argus-evidence-v1" || 0x00
report_data = SHA384(domain || canonical_request || canonical_binding_claims)
```

`report_data_ref` is only a display or logging form of the digest. The security-relevant value is the raw `report_data` placed into the quote and rechecked by the verifier.

### Service Binding Verification

The caller does not trust a quote merely because the quote is valid. The caller must establish that the quote is both:

1. bound to this request, and
2. bound to the service identity it intended to reach.

Argus closes that loop in three checks:

1. Request binding check.
The verifier recomputes the expected `report_data` from the caller's original `EvidenceRequest` and the returned `BindingClaims`. If the quote's `report_data` does not match, the evidence is not bound to this caller request.

2. Service claim binding check.
Because `BindingClaims` are part of the `report_data` hash input, the service cannot return a valid quote for one identity and then attach a different unbound `service_name`, `service_id`, `image_digest`, `launch_digest`, or `spiffe_id` alongside it.

3. Policy target match check.
After verifier normalization, the caller compares `VerifiedClaims` against the intended target, such as `target.service_name`, required service identifiers, reference values, and minimum assurance levels.

This means the caller's confidence does not come from the quote alone. It comes from one attested chain:

1. the caller's original request,
2. the exact binding claims returned in the response,
3. the TEE quote that covers their digest in `report_data`, and
4. the local policy that checks those verified claims against the requested service.

If any one of these links fails, Argus must deny rather than treating the quote as evidence for the intended target service.

## Verifier Contract

The verifier layer is an architectural trust boundary, not just a parsing step. Its job is to validate attestation artifacts, apply verifier-specific trust roots and policy, and normalize the result into one caller-consumable claim surface.

The concrete verifier-facing interface and normalized output types live in [API Contract](./api.md#phase-4-verifier-normalization). This section defines the architectural semantics of that layer.

### Verifier Types

| Verifier Type | What It Proves | Adapter Responsibility |
|---------------|----------------|------------------------|
| Trustee / KBS / Attestation Service | TEE quote validity, TCB status, report data, and reference-value or measurement policy results | Normalize measurements, TCB, and report data into `VerifiedClaims` |
| SPIRE Server / SVID validation | Workload identity issued after attestation at registration or renewal time | Validate SVID chain, SPIFFE ID, trust domain, TTL, and optionally combine it with fresh nonce-bound evidence |
| Composite verifier | Multiple evidence paths merged into one policy result | Apply deterministic precedence and deny rules |

### Composite Merge Rules

1. Quote validity and report-data binding are mandatory gates.
2. Attested identity issuance may raise assurance from L2 to L3, but cannot override failed quote-bound identity.
3. Binding claims take precedence over unbound identity artifacts when they conflict.
4. Freshness violations on policy-required posture claims cause deny.
5. Effective assurance is the minimum of all policy-required verification paths.

Recommended deny-reason precedence:

1. Quote invalid or binding mismatch.
2. Measurement or TCB failure.
3. Hard identity conflict.
4. Attested issuance failure for L3 policy.
5. Posture freshness failure.
6. Optional claim omission.

### Caller Side: Argus Guard

Argus Guard is the caller-side enforcement point. In the current A2S scope, it runs in or next to the agent runtime. Before a sensitive call is made, it:

1. Generates a fresh nonce and builds an evidence request.
2. Fetches target evidence.
3. Verifies the evidence through an external verifier by using the RA adapter.
4. Evaluates local policy and returns `ALLOW` or `DENY`.

Primary modules:

- Guard Engine
- Evidence Fetcher
- RA Adapter

### Service Side: Argus Evidence Provider

Argus Evidence Provider exposes a common evidence API while supporting multiple integration modes. It does not verify caller evidence or make trust decisions.

Primary modules:

- Endpoint Adapter
- Evidence Engine
- Service Runtime Binding

### Service Runtime Binding

Service Runtime Binding is the local integration layer between Argus Evidence Provider and the protected workload instance. Its job is narrow: expose local runtime metadata and optional identity material to the Evidence Engine without turning the business service into an attestation service.

Recommended implementation order:

1. Shared namespace plus mounted metadata for stable service identity.
2. Runtime introspection to confirm the observed process or container instance.
3. UDS only when dynamic posture is required.
4. Loopback-only HTTP posture only when UDS is impractical.

#### Binding Implementation Options

| Integration Mechanism | Typical Claims | Strengths | Limits | Recommended Use |
|-----------------------|----------------|-----------|--------|-----------------|
| Mounted metadata or downward API | Stable service name, workload name, deployment identifiers | Simple, low overhead, no business API change | Not sufficient by itself for live-instance continuity | Baseline identity hints and profile-scoped metadata |
| Runtime introspection | Process identity, container identity, image digest, start time, namespace or cgroup membership | Strong local continuity evidence | May require elevated local visibility | Primary local source for continuity predicates |
| Local UDS posture endpoint | Dynamic posture, readiness mode, local feature flags | Keeps posture off the public network surface | Still needs binding to the observed workload instance | Preferred for dynamic posture when the service can expose local state |
| Loopback-only HTTP posture endpoint | Dynamic posture when UDS is unavailable | Easier adoption for existing services | Larger attack surface than UDS and easier to misconfigure | Fallback only |
| Attested identity material | SPIFFE SVID or equivalent attested workload identity | Strong fit for L3 identity-centric policy | Not every deployment has issuer support | Identity-mode or mixed L2/L3 deployments |

Argus should prefer sources that can participate in the continuity predicate and endpoint-binding predicate. Remote self-description over the service's public API is outside the trusted binding path and must stay diagnostic-only unless independently verified.

### Existing Service Compatibility

Argus is designed to fit existing context, memory, retrieval, and gateway-style services without forcing those services to become attestation-aware business applications.

Recommended integration shape:

1. Keep the business API unchanged.
2. Deploy Argus as a same-pod, same-VM, or same-host evidence sidecar.
3. Expose a separate evidence endpoint such as `/ra/v1/evidence`.
4. Collect local runtime facts through shared namespaces, mounted metadata, local runtime inspection, or local-only posture channels.

This model is compatible with OpenViking-style context gateways and memory services such as TencentDB-Agent-Memory in the specific sense that Argus can protect calls to them as peer services. It is not compatible with treating their ordinary application JSON responses as trust evidence. Argus authenticates the remote service boundary, not in-process plugins, extensions, or skill execution inside that service.

## Deployment Modes

| Mode | Service-Side Integration | Caller-Side Integration | Typical Use Case |
|------|--------------------------|-------------------------|------------------|
| SDK mode | Service exposes `/ra/v1/evidence` through Argus Evidence Provider | Application, agent runtime, or service client calls Argus Guard | First implementation and easiest debugging |
| Envoy mode | Envoy routes `/ra/v1/evidence` to Argus Evidence Provider | Guard fetches evidence through gateway or mesh endpoint | Service mesh and gateway deployments |
| Nginx mode | Nginx exposes evidence endpoint | Guard calls Nginx evidence endpoint | Lightweight reverse proxy deployments |
| Identity mode | SPIRE Agent and SPIRE Server attestor plugins bind TEE attestation to SVID issuance | Guard verifies SVID chain and optionally nonce-bound evidence | Zero-trust workload identity deployments |

### Mode Semantics

`SDK mode` means the caller integrates Argus Guard as an in-process library or application-local component instead of reaching a separate caller-side proxy or daemon first.

In practice, `SDK mode` on the caller side usually pairs with one of these service-side shapes:

1. direct evidence mode: the service side exposes `/ra/v1/evidence` through Argus Evidence Provider without an additional proxy layer,
2. Envoy-backed mode: the caller still uses the SDK locally, but reaches the service-side evidence endpoint through Envoy, or
3. Nginx-backed mode: the caller still uses the SDK locally, but reaches the service-side evidence endpoint through Nginx.

So `SDK mode` is primarily a caller-side integration choice, not a statement that the entire end-to-end deployment must be proxy-free. In Argus v1, the expected default pairing is:

1. caller side in `SDK mode`, and
2. service side in direct evidence mode with Argus Evidence Provider exposing `/ra/v1/evidence`.

`Identity mode` is different in kind. It is not just another transport path for the same evidence endpoint. Instead, it shifts the primary trust surface toward attested workload identity issuance such as SPIFFE or SVID, while optionally retaining nonce-bound evidence for stronger freshness or binding guarantees.

### V1 Integration Strategy

Argus v1 should first support a no-proxy direct path as the minimum closed loop:

1. the caller uses SDK mode,
2. the service side exposes a direct `/ra/v1/evidence` endpoint through Argus Evidence Provider, and
3. the protocol loop is validated without requiring Nginx, Envoy, or service-mesh control-plane dependencies.

This keeps the first implementation focused on evidence generation, binding, verification, and caller-side authorization rather than on proxy integration complexity.

At the same time, Argus should design Nginx and Envoy as standard integration targets rather than as one-off extensions. That means the evidence endpoint, binding semantics, verifier contract, and policy model should remain stable whether the endpoint is reached directly or through a proxy layer.

In later versions, Nginx and Envoy modes can become first-class deployment options for environments that need a standardized ingress path across many heterogeneous services. V1 should preserve that evolution path without making proxy integration a prerequisite for the minimum working trust loop.

### Proxy Identity Boundary

In proxy or service-mesh deployments, Argus must distinguish between:

1. Proxy identity.
2. Workload identity.
3. Composite path identity.

Service mesh control-plane inputs such as xDS state, route config, workload metadata, and mTLS peer attributes are not automatically anchors. A profile must classify the mesh control plane as:

- External trusted authority.
- Corroborator.
- Non-authoritative transport metadata.

If mesh control plane data is required for endpoint-to-workload joining and is not classified as an external trusted authority, it may raise corroboration but must not serve as the sole anchor for workload identity.

## Governance Boundary

Argus v1 defines the verification contract across three governance-dependent inputs, but does not need to implement all three governance systems itself:

1. Profile governance.
2. Collector governance.
3. Reference-value governance.

Argus must surface signer identities, digests, freshness state, and rollback-relevant metadata in verifier results and policy inputs. The publication, PKI, or bundle distribution mechanisms may be provided by external systems.

Extensions such as mesh-authoritative joins, verifier-trusted collectors, advanced ambiguity resolution, or governance-plane orchestration should be treated as profile extensions rather than baseline requirements.

## Implementation Roadmap

### Language Recommendation

The normative interfaces and contracts are written in Rust-style pseudocode, but the recommended v1 prototype is Python because the existing Agent-CC control plane is mostly Python and already has working TDX quote adapter logic under `tc-api`.

Recommended path:

1. Keep normative contracts language-neutral.
2. Implement the v1 prototype in Python under `argus/` using FastAPI, Pydantic, and pytest.
3. Keep evidence binding, canonicalization, and policy semantics backed by cross-language test vectors.
4. Move or rewrite the reusable security-critical core in Rust after the protocol stabilizes.

### Recommended V1 MVP

Argus v1 should define one minimum closed loop that can be implemented and tested end to end before expanding into mesh, collector-heavy, or multi-governance deployments.

Recommended MVP boundary:

1. Python prototype under `argus/`
2. SDK mode on the caller side
3. Direct `/ra/v1/evidence` endpoint exposed by the Evidence Provider
4. Trustee or equivalent verifier for quote and report-data validation
5. Static signed profile loaded locally or from a simple governed bundle
6. No service-mesh-authoritative joins in the base path
7. No verifier-trusted runtime collector required for policy-authoritative claims in the base path
8. Reference-value matching through one governed bundle source

This MVP is primarily a protocol-closed and implementation-closed path. It is intended to reach production-suitable L2 only for deployment profiles whose continuity and endpoint-binding requirements can be satisfied by quote-bound claims, reference-value validation, and profile-approved local binding without a verifier-trusted collector.

Recommended deployment expectations by assurance level:

| Goal | Minimum Operational Shape | Intended Use |
|------|---------------------------|--------------|
| L1 audit or rollout | Sidecar or local evidence collection without policy-authoritative authorization | Development, debugging, disagreement measurement |
| L2 production authorization | Quote-bound identity, profile trust root, reference-value bundle, continuity predicate, and policy-authoritative claim binding | Default production target |
| L3 identity authorization | L2 plus verified attested identity issuance for the policy-relevant identity path | Zero-trust identity-centric deployments |

## Related Documents

- [API Contract](./api.md)
- [Testing And Validation](./tests.md)
