# Confidential Memory Control Plane Architecture

## Summary

The Confidential Memory Control Plane is a future core component for making agent-memory trust decisions explicit, scoped, auditable, and verifiable. It is not a memory framework. It does not standardize how memory is extracted, indexed, recalled, or stored.

The reusable surface is the decision boundary around memory operations:

```text
agent / host / framework adapter
  -> confidential memory control plane
  -> policy decision / lease / key release / egress decision
  -> metadata-only trusted decision ledger
  -> memory framework continues with its native model
```

## Component Boundary

`cmem-control` owns:

- evidence and posture verification contracts
- policy decision contracts
- scoped capability lease contracts
- key-release decision contracts
- egress decision contracts
- metadata-only trusted decision ledger vocabulary
- generic adapter contracts for different memory integration shapes

`cmem-control` does not own:

- OpenViking session storage or archive implementation
- mem0 memory algorithms
- agentmemory consolidation or retrieval pipeline
- TencentDB-Agent-Memory layered memory artifacts
- Letta agent runtime state transitions
- vector stores, embedding providers, or model providers
- raw memory plaintext persistence

## File Organization

The intended future organization is:

```text
core/
  tlog/
  tc-api/
  cmem-control/
    README.md
    docs/
      architecture.md
      api.md
      event-vocabulary.md
      deployment-profiles.md
      threat-model.md
      overview_tasks.md
```

If implementation is later approved, a package such as `cmem_control/` may be added in a separate change. This documentation-only change does not add that package.

## Dependency Stance

`core/tlog` is the direct reusable foundation. Its domain types, deterministic digest helpers, and immutable-log adapter concepts are appropriate for a memory decision ledger because they are not tied to container lifecycle semantics.

`core/tc-api`, TruCon, and `tc-verify` are optional integrations:

- TruCon can serve as an attested sequencer for trusted decision events.
- `tc-verify`-compatible flows can verify exported attested-head evidence.
- `core/tc-api` demonstrates reserve/sign/commit sequencing and same-machine Unix-domain-socket internal transport.

The control plane should not depend on all of `tc-api` as a library because `tc-api` also owns trusted-container build, publish, launch, Docktap, and KBS workflows. Those are out of scope for confidential memory control.

## Trust Model

The trust model separates data-plane memory content from control-plane decisions.

```text
data plane:
  prompts, tool outputs, archives, memories, privacy-restored values

control plane:
  operation type, subject, scope, purpose, policy id, evidence digest,
  lease id, payload digest, result, freshness, and denial reason
```

The trusted decision ledger records the control-plane facts. It must not record session plaintext, prompt text, tool-result plaintext, privacy-restored values, raw memory values, or archive content.

## Integration Shapes

Different memory frameworks need different adapter shapes:

| Shape | Examples | Preferred control point |
|---|---|---|
| SDK/library memory layer | mem0 library mode | SDK wrapper |
| Remote memory service | mem0 server/cloud, OpenViking service | HTTP middleware or gateway |
| MCP/REST shared memory | agentmemory | MCP shim, REST ingress, or server middleware |
| Host-plugin memory framework | TencentDB-Agent-Memory | host adapter hooks |
| Context-engine service | OpenViking for OpenClaw | local verify skill plus service/gateway evidence |
| Stateful agent runtime | Letta | runtime boundary or protected state core |

Gateway deployment is strongest for service-style frameworks. It is not universal enough for embedded SDKs or internal agent runtime state transitions.

## Invariants

- Verification and policy failure must fail closed for context transfer and sensitive materialization.
- Non-confidential gateways must not inspect or persist memory plaintext.
- Materialization of raw evidence, archives, refs, or privacy-restored content must be treated as more sensitive than recall of summaries.
- External LLM and embedding calls must be treated as egress decisions.
- The control plane should standardize trust decisions, not framework memory schemas.

## Documentation-Only Status

This directory currently captures architecture only. It introduces no runtime behavior and no package metadata.