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

These paths are examples, not implemented routes.

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

## Optional TruCon-Compatible Evidence

When TruCon is used, the evidence response may include an attested-head evidence package compatible with `tc-verify --evidence`. That package should bind a TEE quote to a trusted-log head and include a freshness bound.

## Freshness

Evidence must have a bounded validity period. Local verify skills should deny context transfer when evidence is expired or has no acceptable freshness bound under policy.

## Privacy

Evidence responses should not include session content, memory content, archive content, privacy-restored values, or user prompts. Evidence should describe trust state, not memory data.