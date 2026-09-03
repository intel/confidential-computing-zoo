# Argus Architecture

## Purpose And Scope

Argus currently contains two related architectures for establishing runtime
trust in Intel TDX environments: Argus v1 and Argus-SPIFFE.

### Argus v1

Argus v1 is a runtime trust-verification architecture for agent-to-service
(A2S) communication. Before an agent sends sensitive data to a peer service,
it answers one question:

> Is this the expected peer workload, in an acceptable TDX state, for this
> specific request?

The Argus v1 scope covers:

- caller-side allow or deny enforcement,
- service-side generation of nonce-bound TDX evidence,
- verifier-normalized claims, and
- direct, Envoy-routed, or Nginx-routed evidence endpoints.

Service-to-service triggering, cache semantics, and governance-plane
distribution are outside the v1 baseline.

Argus v1 is application-non-invasive because the business API does not need to
produce or verify evidence. It is not necessarily platform-non-invasive:
collecting process, namespace, cgroup, container, or socket information may
require shared namespaces or elevated local visibility.

### Argus-SPIFFE

Argus-SPIFFE integrates Argus TDX evidence with SPIFFE/SPIRE identity. SPIFFE
defines the identity and SVID model, while SPIRE implements attestation,
registration, and identity issuance. The current Node Attestation stage answers
one question:

> May this SPIRE Agent obtain an Agent identity?

The SPIRE identity flow has two stages. Node Attestation establishes the SPIRE
Agent identity. Workload Attestation subsequently identifies a concrete process
or container, applies workload selectors and registration policy, and enables
workload SVID issuance.

The current Argus-SPIFFE implementation covers SPIRE Node Attestation through
the TDX Evidence Provider, external Agent and Server NodeAttestor plugins,
Trustee appraisal, and SPIRE Agent SVID issuance. A successful Node Attestation
does not prove the OpenViking process, image, or business endpoint; those
workload constraints belong to the subsequent SPIRE Workload Attestation stage.

## Design Goals

| Goal | Design Choice |
|------|---------------|
| Protect data before it crosses a peer boundary | Run verification before the business request |
| Avoid changes to business logic | Place evidence generation in a sidecar or infrastructure component |
| Keep authorization with the caller | Make Argus Guard the final policy decision point |
| Support different TDX verifiers | Normalize verifier output through an RA adapter |
| Fail safely | Deny when evidence, verification, or required policy input is unavailable |

## System Architecture

### Argus v1: A2S Verification Flow

```mermaid
flowchart LR
    subgraph Caller[Caller / Agent]
        App[Business client] --> Guard[Argus Guard]
    end

    subgraph Target[Target TDX workload]
        Provider[Evidence Provider]
        Runtime[Runtime Binding]
        TDX[TDX quote source]
        Service[Peer service]
    end

    Verifier[Trustee / Attestation Service]

    Guard -- evidence request + nonce --> Provider
    Provider --> Runtime
    Provider --> TDX
    Provider -- quote + binding claims --> Guard
    Guard -- evidence --> Verifier
    Verifier -- normalized claims --> Guard
    Guard -- ALLOW --> Service
```

#### Components

| Component | Responsibility | Must Not Do |
|-----------|----------------|-------------|
| Argus Guard | Build evidence requests, invoke the verifier, evaluate local policy, and return `ALLOW` or `DENY` | Trust peer self-description without verification |
| Evidence Provider | Collect local binding claims and generate nonce-bound evidence | Make the caller's authorization decision |
| Service Runtime Binding | Observe deployment-owned identity and live runtime facts for the protected workload | Treat a public business API as a trusted identity source |
| RA Adapter / Verifier | Validate TDX evidence and normalize results into `VerifiedClaims` | Override a failed quote or request-binding check |
| ArgusProfile | Define required claims, assurance, verifier expectations, and policy inputs | Turn unsupported local metadata into an authorization anchor |

#### Verification Flow

1. Guard identifies the intended target and generates a fresh nonce.
2. Guard sends an `EvidenceRequest` to the target Evidence Provider.
3. The provider observes the local workload and binds the request and selected
   claims into TDX quote `report_data`.
4. Guard sends the evidence to the configured verifier.
5. The verifier validates and normalizes the evidence.
6. Guard compares the normalized claims with the target and local profile.
7. Guard allows the business request only when every required check succeeds.

This separation is intentional: the target produces evidence, the verifier
validates it, and the caller authorizes the data transfer.

### SPIFFE/SPIRE Identity: SPIRE Node Attestation Flow

This is a SPIRE Node Attestation flow. Argus contributes the guest-local TDX
Evidence Provider and external `argus_tdx` Agent and Server plugins. SPIRE
coordinates the attestation exchange and issues the SPIFFE Agent SVID after
admission.

```mermaid
sequenceDiagram
    participant A as SPIRE Agent / Agent plugin
    participant P as TDX Evidence Provider
    participant T as Linux TSM / TDX
    participant S as SPIRE Server / Server plugin
    participant V as Trustee
    participant C as SPIRE Server CA

    A->>S: AgentHello(proof public key)
    S->>A: Fresh nonce and expiry
    A->>P: Nonce and proof public key over guest-local UDS
    P->>T: Generate nonce-bound Quote
    T-->>P: Raw TDX Quote
    P-->>A: Raw TDX Quote
    A->>S: Quote and transcript signature
    S->>S: Verify slot pin and proof of possession
    S->>V: Quote and canonical runtime data
    V-->>S: Signed EAR
    S->>S: Verify EAR and return AgentAttributes
    C-->>A: Issue Agent SVID after admission
```

1. The Agent plugin sends its operator-provisioned Ed25519 proof public key.
2. The Server plugin checks the key against the configured Agent slot and returns a
   fresh nonce and expiry.
3. The Agent plugin requests a Quote from the guest-local Evidence Provider.
4. The provider binds the Agent identity, nonce, and proof public key into
   TDX `REPORTDATA` and returns the raw Quote.
5. The Agent signs the attestation transcript with the bound proof key.
6. The Server verifies proof of possession and sends the Quote and canonical
   runtime data to Trustee.
7. Trustee appraises the Quote and returns a signed EAR.
8. The Server verifies the EAR and returns `AgentAttributes` to SPIRE.
9. The SPIRE Server CA issues the Agent SVID after admission succeeds.

#### Authority Boundaries

| Component | Authority |
|-----------|-----------|
| TDX Evidence Provider | Generates the raw Quote; it does not appraise evidence or admit the Agent |
| Trustee | Appraises the Quote, collateral, TCB, and policy, then signs the EAR; it does not issue an SVID |
| NodeAttestor Server | Verifies the Agent-slot pin, proof of possession, and EAR, then returns `AgentAttributes` |
| SPIRE Server CA | Issues the Agent SVID after SPIRE accepts the returned attributes |

## Trust And Threat Model

| Threat | Argus Response |
|--------|----------------|
| A peer runs unexpected code, has an unacceptable TCB, or presents the wrong identity | Require quote-backed evidence and verifier policy before the business call |
| Evidence from an earlier request is replayed | Bind a fresh nonce and target context into quote `report_data` |
| A sidecar or workload supplies false or mismatched metadata | Accept policy-relevant claims only when quote-bound, verifier-normalized, or externally anchored |
| Verification is incomplete or unavailable | Fail closed |

Argus trusts the caller-side Guard and its local policy, the configured
verifier and trust roots, and the TDX attestation boundary. It does not trust
peer self-description or local metadata by default.

A valid quote proves attested state and request binding. It does not prove that
all application behavior is benign, that every self-declared identity is true,
or that external state excluded from the evidence is trustworthy.

### Protection Boundary

| Runtime Shape | Covered? | Reason |
|---------------|----------|--------|
| Remote peer service | Yes | Independent A2S trust boundary |
| Same-host separate process | Yes | Separable peer when tied to a live runtime identity |
| Same-pod or same-VM service with an Argus sidecar | Yes | Preferred service-side deployment |
| In-process extension, plugin, or skill | No | Part of the host process trust boundary |

## Evidence Binding Model

### A2S Request Binding

Argus binds the caller request and the provider's selected claims into the TDX
quote:

```text
domain = "argus-evidence-v1" || 0x00
canonical_request = Canon(EvidenceRequest)
canonical_binding_claims = Canon(BindingClaims)
report_data = SHA384(domain || canonical_request || canonical_binding_claims)
```

`Canon(...)` is canonical JSON with sorted keys, UTF-8 encoding, no
insignificant whitespace, and normalized field values. Missing fields and
explicit `null` are distinct. The API contract defines field-level
normalization rules.

The verifier recomputes `report_data` and compares it with the value covered by
the quote. This closes two substitution paths:

- evidence from a different nonce, caller, target, or profile cannot satisfy
  the request; and
- claims attached after quote generation cannot replace the claims covered by
  the quote.

### SPIFFE Node Binding

The SPIRE Node Attestation path binds the Agent identity, Server challenge, and
Agent proof key into TDX `REPORTDATA`:

```text
node_runtime_data =
    LP16("argus.node.tdx.reportdata")
    || LP16("spiffe://argus.local/spire/agent/argus_tdx/openviking-node")
    || nonce
    || proof_public_key

REPORTDATA = SHA384(node_runtime_data) || zero[16]
```

The Agent also signs a transcript digest that binds the proof public key,
nonce, expiry, and Quote digest. The signature proves possession of the key
bound into the Quote; it does not appraise the Quote. Quote, collateral, TCB,
and policy appraisal remain Trustee responsibilities.

### Assurance Levels

| Level | Meaning | Policy Use |
|-------|---------|------------|
| L0 | Metadata from one unverified local source | Diagnostics only |
| L1 | Independent local observations agree | Audit and rollout only |
| L2 | Corroborated claims are quote-bound | Minimum for production authorization |
| L3 | Identity is issued or verified through an attested identity path | Identity-centric authorization |

Quote binding proves that a TEE instance made a claim for this request; it does
not make a self-declared value independently true. Claims such as
`service_name`, `image_digest`, or `spiffe_id` become authoritative only through
profile-approved verification, reference values, attested issuance, or another
external authority.

The current SPIRE Node Attestation path establishes L3 identity for this SPIRE
Agent ID:

```text
spiffe://argus.local/spire/agent/argus_tdx/openviking-node
```

Its returned attributes have the following scope:

- `SelectorValues: nil`.
- `CanReattest: true`.
- No workload identity, Registration Entry, business mTLS, or Guard
  authorization.
- `CanReattest` allows SPIRE to request the full Node Attestation flow again;
  ordinary SVID rotation is not evidence that a new TDX Quote was verified.

### Verification Gates

Guard permits a request only after all applicable gates pass:

1. The quote and TCB are acceptable to the verifier.
2. The quote contains the expected request-and-claims digest.
3. Required measurements or identity anchors match governed expectations.
4. Normalized claims match the intended target and minimum assurance level.
5. The observed live instance joins back to the endpoint the caller will use.

Failure at any gate results in `DENY`.

### Instance And Endpoint Continuity

L2 claims must refer to the live workload behind the target endpoint, not only
to metadata collected at an unrelated time. Typical continuity inputs are:

| Deployment | Continuity Inputs |
|------------|-------------------|
| Kubernetes sidecar | Process start time, pod UID, container identity, and namespace or cgroup membership |
| VM service | VM and process identity, start time, executable or image digest, and local endpoint |
| Bare process | Process identity, start time, executable digest, and local endpoint |

Proxy or service-mesh interception must be declared by the profile. A socket
path or endpoint without current ownership or runtime identity is diagnostic
only. Argus v1 leaves continuity predicates to the deployment integration.

## Verifier Contract

The verifier is a trust boundary. The built-in verifier validates quote
structure, signature, a configured certificate trust anchor, measurements,
and request binding, then returns normalized `VerifiedClaims`. It reports TCB
status as unknown because it does not validate Intel collateral or TCB
freshness. A Trustee/DCAP integration is required when policy depends on those
properties.

The following rules apply regardless of verifier implementation:

1. Quote validity and `report_data` binding are mandatory gates.
2. Attested identity may raise assurance to L3 but cannot override a failed
   quote or conflicting quote-bound identity.
3. Unbound identity artifacts cannot override bound claims.
4. Missing or stale policy-required claims cause denial.
5. Effective assurance is the minimum assurance of all required claim paths.

A deployment must not describe structural quote parsing alone as full remote
attestation. Production verification requires the configured verifier to
validate the applicable collateral, trust chain, TCB, measurements, and
reference values.

Concrete adapter interfaces and claim types are defined in the
[API Contract](./api.md#phase-4-verifier-normalization).

## Deployment Architecture

### A2S V1 Default

The minimum v1 deployment uses:

- Guard in or next to the caller,
- an Evidence Provider beside the target service,
- a direct `/ra/v1/evidence` endpoint,
- a TDX-capable verifier, and
- a local `ArgusProfile` or equivalent bundled configuration.

The business service and Evidence Provider may start in parallel. The provider
is evidence-ready only after its profile, identity source, runtime binding
inputs, and quote path are available. Before that point, the evidence endpoint
must return an error rather than partial authorization-grade evidence.

### SPIFFE/SPIRE Identity: SPIRE Node Attestation

The Agent plugin and TDX Evidence Provider run on the attested node. The plugin
calls the provider over a guest-local UDS, while Agent-side and Server-side
plugin messages travel inside the SPIRE Agent-to-Server enrollment stream. The
Server plugin calls Trustee over HTTPS and verifies the independently signed
EAR before returning `AgentAttributes` to SPIRE.

### Integration Modes

| Mode | Evidence Path | Use Case |
|------|---------------|----------|
| Direct | Guard calls the Evidence Provider directly | V1 default and easiest debugging |
| Envoy | Envoy routes the evidence endpoint | Service mesh deployments |
| Nginx | Nginx routes the evidence endpoint | Lightweight proxy deployments |

The evidence protocol and binding rules do not change between modes. In proxy
deployments, proxy identity, workload identity, and endpoint-to-workload
continuity remain separate concepts. Mesh metadata is an authorization anchor
only when the profile explicitly trusts the control plane as an authority;
otherwise it is corroborating or diagnostic input.

### Runtime Binding Sources

Preferred sources, from baseline to stronger live-instance evidence, are:

1. deployment-owned mounted metadata for stable identity hints,
2. runtime introspection for process, container, namespace, and endpoint joins,
3. a local UDS for dynamic posture, and
4. loopback HTTP only when UDS is impractical.

Remote self-description from the protected service's public API is not a
trusted binding source unless independently verified.

## TC-API Integration

TC-API is an optional source of deployment and workload metadata. When enabled,
the Evidence Provider queries TC-API through `TcApiClient`, merges permitted
metadata with local runtime observations, and includes selected values in
`BindingClaims` before quote generation.

```mermaid
sequenceDiagram
    participant G as Guard
    participant P as Evidence Provider
    participant T as TC-API
    participant Q as TDX Quote Source

    G->>P: EvidenceRequest
    P->>T: Query workload metadata
    T-->>P: Workload identity and image metadata
    P->>Q: Generate quote over request and claims digest
    Q-->>P: TDX quote
    P-->>G: Evidence and BindingClaims
```

TC-API metadata is not trusted merely because it came from TC-API. Its policy
authority depends on the profile, its binding into the quote, and any required
reference-value or verifier checks. When TC-API is disabled, the provider uses
the configured local runtime-binding path.

Endpoint details and environment variables are documented in
[Configuration](./configuration.md#evidence-provider-configuration) and the
[API Contract](./api.md).

## Security Analysis

Argus protects the A2S decision to release data to a peer and integrates TDX
evidence into SPIRE node admission. It does not replace transport encryption,
storage encryption, or workload hardening.

### Data in Transit

The relevant paths are caller-to-Guard, Guard-to-Evidence Provider,
Evidence Provider-to-TC-API, Guard-to-verifier, and the subsequent business
request to the peer service.

For SPIRE Node Attestation, the Agent plugin calls the TDX Evidence Provider
over a guest-local UDS, the Agent and Server plugins exchange messages through
the SPIRE enrollment stream, and the Server plugin calls Trustee over HTTPS.
HTTPS authenticates the Trustee endpoint, while the EAR signature independently
authenticates the appraisal result.

- The evidence-binding protocol protects evidence integrity and freshness. A
  modified request, substituted claim set, or replayed response fails the
  `report_data` check.
- Evidence binding does not encrypt traffic or authenticate the network
  endpoint that carries it. The default local and Compose examples use plain
  HTTP and are suitable only inside a trusted local or isolated network path.
- Production deployments must use TLS, mutual TLS, or an authenticated service
  mesh for every path that crosses a trust boundary. Bearer tokens, identity
  material, evidence, and business data must not traverse an unprotected
  network.
- Transport identity and attested workload identity are complementary. The
  deployment must join the authenticated endpoint to the workload identity
  accepted by Guard; a valid quote alone does not prevent traffic redirection
  after verification.

### Data at Rest

Argus does not maintain an authoritative evidence database or trusted history.
Evidence and normalized claims are normally transient process data. Persistent
inputs may include profiles, policy files, reference values, CA certificates,
service tokens, identity material, and operational logs.

- File permissions, secret mounts, host or volume encryption, rotation, backup,
  and deletion of those inputs are deployment responsibilities.
- Tokens and private identity material should be provided through a secret
  manager or access-controlled memory-backed mount rather than embedded in
  images, Compose files, or source-controlled configuration.
- Quotes and claims are not necessarily confidential, but they may reveal
  workload identity, measurements, topology, and runtime metadata. Logs and
  retained API responses should therefore follow the deployment's data
  classification and retention policy.
- Argus does not currently provide automatic at-rest encryption, secure
  deletion, or persistence recovery guarantees. Using `tmpfs` can reduce disk
  persistence but makes state volatile and does not encrypt data while the
  guest is running.

### Data in Use

When Guard, the Evidence Provider, and the protected workload run inside a TDX
guest, their process memory is protected from the host and hypervisor according
to the TDX threat model. Requests, claims, policy inputs, tokens, and business
data are still plaintext inside the guest while being processed.

- TDX does not protect against a compromised guest kernel, guest root, or
  another process admitted to the same trust boundary with sufficient access.
- Sidecar permissions needed for runtime binding, such as shared namespaces,
  device access, or elevated capabilities, enlarge the trusted computing base
  and should be restricted to the minimum required by the profile.
- Argus authorizes a call before data transfer; it does not continuously protect
  the peer after the decision. Deployments must minimize the interval between
  verification and use and enforce endpoint-to-instance continuity to reduce
  time-of-check/time-of-use risk.
- Sensitive values may remain in process memory until released by the runtime.
  The current design does not guarantee memory locking or zeroization, so
  callers should avoid placing unnecessary secrets in evidence or logs.

### Residual Risks

Argus does not prove business-logic correctness, prevent compromise that
preserves accepted measurements, secure data after an authorized peer receives
it, or protect external systems outside the attested and authenticated path.
Those controls remain part of workload, platform, network, and data-governance
security.

## Governance Boundary

Argus defines how three governed inputs affect verification:

- `ArgusProfile` requirements,
- collector identity and authority, and
- reference-value provenance and freshness.

Argus v1 does not define a remote publisher, signing service, bundle API, or
operator workflow for those inputs. Deployments may provide those systems, but
Guard must receive enough signer, digest, freshness, and rollback information
to enforce local policy.

## Argus V1 Baseline

The baseline is intentionally narrow:

- A2S verification only.
- Rust Guard and Evidence Provider implementations.
- Direct evidence endpoint as the minimum closed loop.
- Quote and request-binding validation through a TDX-capable verifier.
- Local profile configuration.
- No verifier-trusted collector or mesh-authoritative join required by the base
  path.

Production L2 is possible only when the deployment satisfies its continuity,
endpoint-binding, reference-value, and policy-authority requirements. L3 also
requires verified attested identity issuance for the policy-relevant identity.

## Related Documents

- [API Contract](./api.md): protocol fields, normalized claims, profiles, and
  policy types.
- [Configuration](./configuration.md): runtime settings and verifier options.
- [Quick Start](../README.md#quick-start): build and local deployment workflow.
- [Troubleshooting](./troubleshooting.md): operational diagnosis.
