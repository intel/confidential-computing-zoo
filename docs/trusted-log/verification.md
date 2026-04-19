# tc-verify Design

## Purpose

This document defines the verification design for `tc-verify`, the operator-facing tool used to validate trusted-log chains for tc-api workloads.

The goal of `tc-verify` is not only to replay public event history from Rekor, but also to support remote verification that binds application-layer events to attested TEE state.

This document focuses on:

- what `tc-verify` verifies
- which inputs it should consume
- how Event Log 0 and current chain head evidence fit together
- which event fields are required for operator verdicts

This document does not define wire-level API details for every evidence field. Those should evolve with implementation changes and OpenSpec artifacts.

## Positioning

`tc-verify` is an operator and auditor tool, not a TruCon control-plane component.

The intended long-term boundary is:

- **TruCon** produces and maintains trusted event state inside the CVM.
- **Rekor** stores the public immutable event chain.
- **tc-verify** consumes public chain history plus exported attested evidence to produce verification results.

In the current repository, `tc-verify` is packaged together with `tc-api`, but its design should be treated as an external verification surface rather than an internal TruCon subsystem.

## Scope

`tc-verify` is responsible for:

- replaying immutable event history from Rekor
- validating Event Log 0 as the epoch baseline anchor
- validating signer identity policy for committed events
- consuming exported evidence that binds the current chain head to current attested CVM state
- producing operator-facing verdicts in human-readable and machine-readable form

`tc-verify` is not responsible for:

- sequencing events
- maintaining local queue state
- extending RTMR
- driving TruCon submission or retry behavior
- serving as the source of truth for chain state

## Design Principles

1. **Public replay is primary**
   Rekor is the source of truth for replaying immutable event history.
2. **TEE binding is explicit**
   The verifier should consume explicit attested evidence for the current chain head rather than implicitly trusting live internal service state.
3. **Baseline and current state are different things**
   Event Log 0 anchors the start of a chain epoch; a separate attested checkpoint binds the current chain head to current CVM state.
4. **Operator semantics stay simple**
   The first version should focus on per-flow verification profiles rather than whole-system lifecycle reasoning.
5. **Internal and external interfaces are distinct**
   TruCon internal APIs are operational control surfaces; they are not the final external verifier contract.

## Chain Concepts

The verifier should distinguish the following fields:

- `chain_id`: logical chain identity. In the current model this is workload-scoped and should be treated as one chain epoch in v1.
- `sequence_num`: monotonic local sequence number assigned by TruCon within a chain.
- `head_log_id`: the latest confirmed Rekor entry ID for the chain.
- `mr_value`: the locally recorded RTMR[2] value after extending the event digest for a given record.

These fields answer different questions:

- `chain_id` answers: which chain are we talking about?
- `sequence_num` answers: which event position inside the chain?
- `head_log_id` answers: which Rekor entry is the latest confirmed public tail?
- `mr_value` answers: which local measurement state corresponds to that point in the chain?

## Event Log 0

Event Log 0 is the baseline anchor and epoch anchor for a chain.

`tc-verify` should treat Event Log 0 as the first record of trust for a chain epoch.

The minimum baseline data expected from Event Log 0 is:

- `baseline_rtmr`
- `ccel_digest`
- `pub_key`

Roles:

- `baseline_rtmr`: captures the initial RTMR[2] snapshot for the epoch
- `ccel_digest`: captures the platform boot baseline digest
- `pub_key`: anchors chain origin to the TEE-generated key used to sign Event Log 0

Event Log 0 answers: where did this chain epoch begin, and what trusted platform baseline did it start from?

Event Log 0 does **not** answer: what is the current attested state of the CVM right now?

## Attested Head Evidence

Remote verification requires more than Event Log 0. It also needs attested evidence for the current chain head.

The verifier should consume an exported evidence package that binds the current chain head to the current attested CVM state.

### Minimum Evidence Package Fields

The first version should require at least:

- `chain_id`
- `sequence_num`
- `head_log_id`
- `mr_value`
- `quote`

Optional but useful additions:

- `head_event_digest`
- `generated_at`
- `report_data_binding`
- `tee_type`

### Why This Package Exists

Rekor alone can prove that a chain of signed event records exists and can be replayed.
It cannot, by itself, prove that the current CVM still endorses the current chain head.

The evidence package exists to bridge that gap:

- Rekor proves public history.
- Event Log 0 proves baseline origin.
- Attested head evidence proves the current head is bound to the current CVM state.

### Evidence and Rekor Association

The evidence package must be explicitly associated with the Rekor chain.

At minimum, the verifier should require:

- `chain_id`
- `head_log_id`
- `sequence_num`

Without those fields, the evidence package is only a detached TEE snapshot and cannot be tied to a specific public event chain.

## Verification Inputs

### Required Inputs

The preferred long-term inputs for `tc-verify` are:

1. Rekor chain history, resolved from `head_log_id`
2. Exported attested head evidence package

### Transitional Inputs

The current implementation also consumes live TruCon APIs for:

- `GET /chain-state/{chain_id}`
- `GET /verify-chain/{chain_id}`

This is acceptable for in-CVM and transitional operational workflows, but the design should not require live TruCon connectivity as the final external verifier model.

## Verification Flow

The intended external verification flow is:

1. Resolve the target `chain_id` and current `head_log_id` from exported evidence.
2. Load immutable entries from Rekor starting at `head_log_id`.
3. Traverse backward through the chain and replay entry digests and event digests.
4. Validate Event Log 0 and extract `baseline_rtmr`, `ccel_digest`, and `pub_key`.
5. Validate the signer policy for non-baseline events.
6. Validate that replayed chain state reaches the attested head described by the evidence package.
7. Validate that the evidence package's `mr_value` is consistent with the quote-backed TEE state.
8. Return a per-flow verdict and supporting diagnostics.

```text
Rekor chain replay
      |
      v
validate Event Log 0
      |
      v
match exported attested head evidence
      |
      v
operator verdict
```

## Verification Profiles

The first version should verify flows independently rather than trying to compute one global workload verdict.

Recommended profiles:

- `build`
- `publish`
- `launch`
- `docktap-runtime`

Each profile should define:

- required fields
- hard failures
- warnings

### Build Profile

Expected fields:

- output image digest
- build input digest(s)
- build result status
- optional SBOM digest

Hard fail:

- missing output image digest
- build reported success but missing identity of built artifact
- malformed or missing required input digest

Warning:

- SBOM digest missing
- non-critical build metadata absent

### Publish Profile

Expected fields:

- image digest
- target registry or repository
- publish result
- optional signature or attestation verification result

Hard fail:

- missing image digest
- publish reported success but no stable published identity
- signature verification required by policy but missing or failed

Warning:

- non-critical provenance fields absent

### Launch Profile

Expected fields:

- image digest
- signature verification result
- SBOM verification result
- launch configuration digest
- workload identifier / chain identifier
- instance identifier when container context exists
- create/start result

Hard fail:

- missing image digest
- signature verification required but missing or failed
- SBOM verification required but missing or failed
- missing launch configuration digest
- create or start failed
- missing workload or instance identity when required

Warning:

- missing optional environment metadata
- missing non-critical labels or annotations

### Docktap Runtime Profile

Expected fields:

- operation type (`pull`, `create`, `start`, `stop`, `rm`)
- workload identifier / chain identifier
- instance identifier for container-scoped operations
- image reference or image digest
- operation result

Hard fail:

- missing workload identifier for a workload-scoped operation
- missing container identity for container-scoped operation
- successful operation missing audited target identity

Warning:

- missing auxiliary metadata that does not change audit meaning

## Signer Policy

The initial signer policy should remain simple.

Recommended baseline rules:

- Event Log 0 is anchored by the embedded `pub_key`.
- Non-baseline events are checked against an allowlist of signer identities.
- If operator policy needs source separation, the verifier may use a simple mapping such as:
  - tc_api-originated event types -> allowed tc_api identities
  - docktap-originated event types -> allowed Docktap identities

The first version should avoid a full policy DSL for signer routing.

## Chain Epoch Model

The first version should assume:

- each CVM reboot begins a new chain epoch
- Event Log 0 anchors the new epoch
- one workload flow or launch epoch maps to one chain in practice

The first version should **not** require:

- explicit close markers for old chains
- stitching one workload across multiple chain epochs
- modeling superseded or closed chain states

These concerns can be added later once the operator evidence model is stable.

## Packaging Guidance

`tc-verify` should be treated as an operator-facing package, even if it continues to live in the same repository as `tc-api` and TruCon.

Practical guidance:

- keep a standalone CLI entry point
- avoid long-term dependence on internal TruCon runtime assumptions
- prefer stable verifier inputs (`Rekor + evidence package`) over direct reliance on live TruCon internals

The current repository layout may continue to co-locate `tc-verify` with `tc-api`, but its design should remain separate from the TruCon control-plane boundary.

## Open Design Questions

- Which exact quote fields should be required in the evidence package for current-head binding?
- Should the evidence package contain `head_event_digest` in addition to `mr_value`?
- How should operator tooling fetch exported evidence in production deployments?
- Should transitional TruCon-backed verification remain a fallback mode or be removed once exported evidence is available?

## Related Documents

- [architecture.md](architecture.md) — trusted-log internal architecture and replay model
- [api.md](api.md) — Python and REST API contracts
- [README.md](README.md) — module overview and operational entry points
- [../architecture.md](../architecture.md) — top-level system architecture