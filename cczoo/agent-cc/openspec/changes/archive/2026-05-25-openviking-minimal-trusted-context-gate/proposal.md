## Why

OpenClaw currently lacks a minimal trust gate that can verify an OpenViking confidential memory target before sending context. The architecture and documentation are in place, but the first implementation slice still needs a narrow proposal that turns the design into an apply-ready change without expanding immediately into gateway-wide policy, full internal hooks, key release, or broader control-plane runtime work.

## What Changes

- Add a minimal OpenViking evidence surface contract for context-send trust establishment.
- Add a local OpenClaw verify-skill capability that fetches and validates OpenViking evidence before context transfer.
- Add a short-lived five-minute trust-cache model so OpenClaw does not need to re-run full verification on every single send while still failing closed on expiry or verification errors.
- Add explicit allow or deny semantics for `send_context`, where deny blocks context transfer rather than degrading into partial send behavior.
- Add a minimal metadata-only decision-record contract for `context_send.allow` and `context_send.deny` outcomes.
- Exclude key release, full capability-lease semantics, gateway-wide route policy, and OpenViking internal materialize or privacy-restore hooks from this change.

## Capabilities

### New Capabilities
- `openviking-trusted-context-gate`: Defines the minimum trust-establishment flow for OpenClaw to verify OpenViking evidence, cache verified trust for five minutes, and allow or deny context transfer.
- `openviking-evidence-surface`: Defines the evidence and posture claims that OpenViking must expose so the local verify skill can make a fail-closed context-send decision.

### Modified Capabilities
- None.

## Impact

- Affects future OpenClaw local verify-skill behavior for OpenViking integration.
- Affects future OpenViking evidence or posture endpoints and their claim set.
- Introduces a narrow first implementation slice for `core/cmem-control` decision semantics without requiring the full runtime package.
- Reuses existing `tc-verify` and attested-head evidence concepts for compatibility, but does not require the entire `tc-api` runtime as a direct dependency.