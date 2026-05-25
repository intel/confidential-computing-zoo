# OpenClaw Local Verify Skill Contract

This directory documents the intended local verify skill for OpenClaw. It does not contain runnable skill code in this change.

## Purpose

Before OpenClaw sends context to OpenViking, it should call a local verify skill. The skill verifies OpenViking, gateway, or sidecar evidence and returns an allow or deny result.

## Inputs

Expected inputs include:

- target OpenViking or gateway URL
- expected deployment id or policy id
- expected evidence freshness window
- operation, usually `send_context`
- optional workspace or tenant scope hash
- optional policy file path

The skill should not require prompt plaintext or session plaintext to decide whether context transfer is allowed.

## Evidence Verification

The skill is expected to use evidence-backed verification semantics compatible with the repository's `tc-verify` and attested-head evidence model when that integration is available.

Verification should check:

- evidence shape and signature or quote binding
- freshness and expiration
- expected deployment or service identity
- ledger chain and head binding
- policy id and policy version compatibility
- egress and privacy-restore posture claims when required

## Outputs

Allow result:

```json
{
  "result": "allow",
  "decision_id": "cmem-decision-opaque",
  "evidence_digest": "sha384:...",
  "policy_id": "openviking-context-send",
  "expires_at": "2026-05-25T12:10:00Z"
}
```

Deny result:

```json
{
  "result": "deny",
  "reason": "verification_unavailable",
  "fail_closed": true
}
```

## Fail-Closed Behavior

The skill must deny context transfer when:

- evidence cannot be fetched
- evidence is expired
- quote or ledger-head binding fails
- policy cannot be loaded or evaluated
- expected deployment identity does not match
- required posture claims are missing
- verification tooling returns an error

## Non-Goals

The local verify skill should not perform memory recall, archive expansion, privacy restore, or memory extraction. It is a trust gate, not a memory client.