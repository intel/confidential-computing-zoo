# OpenViking Confidential Memory Adapter API Contracts

This document describes contracts and examples for a future OpenViking/OpenClaw integration with the Confidential Memory Control Plane. It is not a runtime API implementation.

## Local Verify Skill Flow

OpenClaw should call a local verify skill before sending context to OpenViking.

```text
OpenClaw prepares context
  -> calls local verify skill
  -> skill fetches evidence/posture from OpenViking, gateway, or sidecar
  -> skill verifies evidence using tc-verify-compatible semantics
  -> skill returns allow or deny
  -> OpenClaw sends context only on allow
```

Failure semantics are fail closed. If evidence is missing, expired, malformed, unverifiable, or policy-incompatible, the skill denies context transfer.

The current reference implementation in this repository lives in `core/tc-api/tc_api/trucon/openviking_context_gate.py` and is exposed as `tc-openviking-verify-context`.

## Evidence Source Options

Evidence may be exposed by:

- OpenViking itself through a future confidential evidence endpoint
- an external verifier/policy gateway
- a sidecar bound to the same confidential deployment

The low-intrusion path may start with gateway-hosted or sidecar-hosted evidence. The complete target state should bind evidence to the OpenViking confidential core.

For the current minimal implementation slice, the repository uses a dedicated evidence surface and posture surface exposed by the reference service rather than a gateway-only contract.

## Minimum Evidence and Posture Claims

The following claims are expected at the contract level:

| Claim | Purpose |
|---|---|
| `deployment_id` | Identifies the OpenViking deployment or gateway deployment |
| `service_instance_id` | Identifies the specific service instance |
| `tee_type` | Names the confidential computing technology, such as `tdx` |
| `measurement` or `measurement_ref` | Binds policy to measured runtime state |
| `ledger_chain_id` | Identifies the trusted decision ledger chain |
| `ledger_head_id` | Identifies the latest trusted decision ledger head |
| `evidence_digest` | Digest of exported evidence material |
| `generated_at` | Evidence generation time |
| `expires_at` | Evidence freshness bound |
| `policy_id` | Policy applied to this trust contract |
| `policy_version` | Policy version used for decision compatibility |
| `egress_mode` | Declares external model/embedding egress posture |
| `privacy_restore_policy` | Declares whether privacy restore requires verified policy/evidence |

When TruCon integration is used, attested-head evidence should be compatible with `tc-verify --evidence` style verification.

## Verify Skill Result

The local skill should return a small result object:

```json
{
  "result": "allow",
  "decision_id": "cmem-decision-opaque",
  "verified_target": "openviking",
  "policy_id": "openviking-context-send",
  "policy_version": "2026-05-25",
  "evidence_digest": "sha384:...",
  "expires_at": "2026-05-25T12:10:00Z"
}
```

For denial:

```json
{
  "result": "deny",
  "reason": "evidence_expired",
  "fail_closed": true
}
```

## Route Classes

The adapter should classify OpenViking behavior before policy evaluation:

| Route or behavior | Operation class |
|---|---|
| system status and readiness | posture |
| search/find | recall |
| session context | recall |
| session messages | observe |
| session commit | commit |
| content read | materialize |
| archive expansion | materialize |
| privacy placeholder restore | privacy_restore and materialize |
| external LLM calls | egress |
| external embedding calls | egress |

## Policy Defaults

Recommended default posture:

- context transfer requires verified evidence
- materialization requires stronger policy than recall
- privacy restore requires verified confidential boundary
- external egress requires explicit allow
- unavailable policy or evidence denies sensitive operations

The current minimal implementation also reuses successful `send_context` verification for at most five minutes when the cached verification key still matches target URL, service instance, measurement, ledger head, and policy version.

## Non-Implementation Notice

This document does not add endpoints or skill code. It defines the contract for a future implementation proposal.