# Confidential Memory Control Plane API

This document describes API families at the contract level. It is not an implementation specification for a server, package, or protocol binding. A future implementation may expose these contracts over REST, MCP, Unix sockets, local SDK calls, or a combination of those surfaces.

## Common Request Shape

Control-plane calls should be metadata-oriented by default:

```json
{
  "operation": "recall",
  "subject": {
    "agent": "openclaw",
    "user_hash": "sha256:...",
    "workspace_hash": "sha256:..."
  },
  "resource": {
    "framework": "openviking",
    "scope": "tenant:opaque/project:opaque",
    "sensitivity": "private-memory"
  },
  "context": {
    "purpose": "assemble-context",
    "requires_materialization": false,
    "egress_intent": "none"
  }
}
```

Requests should carry scopes, hashes, purposes, evidence references, and policy identifiers instead of memory plaintext.

## Evidence API

Evidence APIs establish whether a memory service, gateway, sidecar, or runtime is the expected trusted instance.

Contract responsibilities:

- accept attested-head evidence or a reference to evidence
- verify evidence freshness and quote binding
- bind evidence to a deployment identity and ledger head
- return a machine-readable verdict

Typical operations:

- `getEvidence(target)`
- `verifyEvidence(evidence, policy)`
- `getPosture(target)`

Evidence-backed flows should be compatible with the repository's existing `tc-verify` and attested-head evidence concepts when TruCon integration is used.

The current minimal OpenViking reference implementation in `core/tc-api/tc_api/trucon/` follows this compatibility model by exposing a dedicated evidence surface, embedding attested-head evidence material, and validating context-send decisions without requiring the full control-plane runtime package.

## Policy Decision API

Policy APIs answer whether a subject can perform an operation on a memory resource for a stated purpose.

Typical operations:

- `authorize(operation, subject, resource, context)`
- `explainDecision(decision_id)`

Decision outcomes:

- `allow`
- `deny`
- `fail_closed`
- `degraded`

The policy decision result should include a decision identifier, policy identifier, policy version, optional lease reference, ledger event reference, and denial reason when applicable.

## Capability Lease API

Capability leases scope a short-lived authorization to a subject, resource, operation set, purpose, and TTL.

Typical operations:

- `issueLease(subject, resource, operations, ttl, purpose)`
- `validateLease(lease, operation, resource)`
- `revokeLease(lease_id)`

Lease material should be bound to claims such as subject, scope, allowed operations, expiration, evidence head, and policy version. Leases should not carry memory plaintext.

## Key-Release API

Key-release APIs decide whether a service, runtime, or tenant scope can receive key material or key handles.

Typical operations:

- `requestKeyRelease(evidence, resource, purpose)`
- `revokeKeyLease(lease_id)`

Key release should require evidence verification and policy authorization. Actual key broker implementation is out of scope for this documentation-only change.

## Egress Decision API

Egress APIs decide whether memory-derived data can leave the confidential boundary.

Typical operations:

- `authorizeEgress(operation, provider, payload_class, destination, purpose)`

Egress decisions should cover external LLMs, embedding providers, analytics systems, telemetry sinks, export paths, and remote debugging surfaces. The request should describe payload class and destination, not payload plaintext.

## Audit and Ledger API

Audit APIs record metadata-only security decisions into a trusted decision ledger.

Typical operations:

- `recordDecision(decision_metadata)`
- `recordDenial(denial_metadata)`
- `getLedgerHead(chain_id)`
- `exportEvidence(chain_id)`

Ledger entries should contain canonical metadata such as operation, result, policy id, subject hash, resource scope hash, evidence digest, payload digest, lease id hash, and timestamps. They must not contain prompt text, tool-result plaintext, raw memory content, archive plaintext, or privacy-restored values.

The current minimal OpenViking gate narrows this to metadata-only `context_send.allow` and `context_send.deny` decision records.

## Failure Semantics

The default security posture is fail closed:

- if evidence cannot be verified, deny sensitive operations
- if policy cannot be evaluated, deny context transfer and materialization
- if ledger recording is required by policy and unavailable, deny or explicitly return `fail_closed`
- if egress policy is unavailable, deny external calls that would carry memory-derived data