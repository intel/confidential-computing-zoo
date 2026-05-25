# OpenViking Evidence and Posture Endpoint Spec

This is a documentation-only contract for a future OpenViking, gateway, or sidecar evidence surface.

## Purpose

The evidence surface allows OpenClaw local verify skills and verifier/policy gateways to determine whether the target OpenViking confidential memory service is trusted before context is sent.

## Candidate Endpoints

If implemented inside OpenViking, candidate paths could be:

```text
GET /api/v1/confidential/evidence
GET /api/v1/confidential/posture
GET /api/v1/confidential/ledger/head
```

If implemented by a gateway or sidecar, equivalent paths may be exposed under a gateway namespace such as:

```text
GET /cmem/evidence
GET /cmem/posture
GET /cmem/ledger/head
```

These paths are examples for an OpenViking-native deployment.

The current reference implementation in this repository exposes equivalent dedicated surfaces from the reference trust service at:

```text
GET /confidential/evidence/{chain_id}
GET /confidential/posture/{chain_id}
```

This preserves the same separation between evidence and posture while keeping the first implementation slice inside the available `core/tc-api` runtime.

## Required Claims

Evidence and posture responses should include:

- `deployment_id`
- `service_instance_id`
- `tee_type`
- `measurement` or `measurement_ref`
- `ledger_chain_id`
- `ledger_head_id`
- `evidence_digest`
- `generated_at`
- `expires_at`
- `policy_id`
- `policy_version`
- `egress_mode`
- `privacy_restore_policy`

In the current reference implementation, the evidence response additionally includes an embedded `attested_head_evidence` object and uses `measurement_ref` and `ledger_head_id` as the direct verification fields consumed by the local context gate.

## Optional TruCon-Compatible Evidence

When TruCon is used, the evidence response may include an attested-head evidence package compatible with `tc-verify --evidence`. That package should bind a TEE quote to a trusted-log head and include a freshness bound.

## Freshness

Evidence must have a bounded validity period. Local verify skills should deny context transfer when evidence is expired or has no acceptable freshness bound under policy.

The current reference implementation sets the first trust window to five minutes, aligned with the existing 300-second TTL posture already used in TruCon.

## Privacy

Evidence responses should not include session content, memory content, archive content, privacy-restored values, or user prompts. Evidence should describe trust state, not memory data.