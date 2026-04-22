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

For the current repository implementation, one practical nuance matters: a Sigstore bundle produced by the live signing path can contain richer DSSE payload material than a later raw Rekor readback alone exposes in directly normalized form. The verifier may use bundle-derived or cached payload material as a local retrieval aid, but it no longer treats that cache-assisted reconstruction as public proof truth. Historical continuity and Event Log 0 origin count as publicly verified only when those facts can be materialized from Rekor-auditable entry data.

The current implementation extends that retrieval aid with `OciBundleMirror`, a non-authoritative OCI artifact mirror keyed by `payload_hash`. When a public Rekor DSSE entry is hash-only, the verifier can rehydrate the current head or predecessor bundle payload from the mirror while still treating Rekor inclusion as the authoritative public anchor.

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
- `pub_key`: anchors chain origin to the TEE-generated key material recorded in Event Log 0 during baseline initialization

Event Log 0 answers: where did this chain epoch begin, and what trusted platform baseline did it start from?

Event Log 0 does **not** answer: what is the current attested state of the CVM right now?

For every non-`default` chain, `tc-verify` must require that the first replayed immutable record is Event Log 0. A workload chain that begins with a business or runtime event instead of `chain.init` is structurally invalid even if later records, signatures, and attested-head evidence otherwise look well-formed.

## Attested Head Evidence

Remote verification requires more than Event Log 0. It also needs attested evidence for the current chain head.

The verifier should consume an exported evidence package that binds the current chain head to the current attested CVM state.

### Minimum Evidence Package Fields

The first version requires these top-level fields:

- `version`
- `tee_type`
- `chain_id`
- `sequence_num`
- `head_log_id`
- `mr_value`
- `generated_at`
- `quote`
- `report_data_binding`

The first version may additionally carry:

- `head_event_digest`
- `quote_format`
- `expires_at`
- `extensions`

The v1 contract is intentionally JSON and versioned so TruCon, `tc-verify`, and tests can share one canonical evidence shape before any export transport is chosen.

### Report Data Binding

`report_data_binding` records how the evidence package is tied to quote-backed report data.

The first version requires:

- `algorithm`: the digest algorithm used to derive the bound value
- `bound_fields`: the ordered list of fields included in the binding
- `expected_value`: the canonical digest value expected to appear in quote-bound report data

For v1, `bound_fields` must be ordered as:

- `chain_id`
- `sequence_num`
- `head_log_id`
- `mr_value`

This ordering is part of the contract. External verifiers should not infer field order from implementation details.

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

In v1, `mr_value` is also part of the quote-backed binding. That keeps the evidence package tied not only to a public chain head position but also to the measured RTMR[2] state expected at that position.

Without those fields, the evidence package is only a detached TEE snapshot and cannot be tied to a specific public event chain.

### Event Log 0 Boundary

The attested head evidence package does not duplicate Event Log 0 baseline data.

In particular, v1 evidence packages do not need to embed:

- `baseline_rtmr`
- `ccel_digest`
- Event Log 0 payload bodies

Those fields remain part of Rekor-backed epoch replay. Event Log 0 answers where the chain epoch began; attested head evidence answers which public head the current CVM is endorsing now.

The same boundary applies to predecessor continuity: exported evidence does not replace the signed predecessor contract carried in replayed immutable entries, and optional evidence extensions must not be interpreted as a substitute for publicly replayable history.

### Export Surface

The current producer-side export surface is a strict read-only TruCon endpoint:

- `GET /evidence/{chain_id}`

v1 export semantics are intentionally narrow:

- export only the latest confirmed public head for the chain
- fail if the chain has no confirmed `head_log_id`
- fail if quote acquisition fails
- fail if quote-backed report data does not match the producer-computed `expected_value`

In other words, the export surface does not return degraded evidence for pending-only chains. Pending local state can still be observed through internal TruCon control APIs, but it is not eligible for external evidence export.

For v1, TruCon computes `report_data_binding.expected_value` from canonical serialization of the ordered bound fields and then compares that derived value against the quote-backed report-data value. The quote proves TEE endorsement; it does not define the contract value by itself.

## Verification Inputs

### Required Inputs

The preferred long-term inputs for `tc-verify` are:

1. Rekor chain history, resolved from `head_log_id`
2. Exported attested head evidence package

### Transitional Inputs

The current implementation treats exported evidence as the supported external operator input. Live TruCon APIs are retained only as explicit internal troubleshooting inputs for tightly coupled or in-CVM workflows:

- `GET /chain-state/{chain_id}`
- `GET /verify-chain/{chain_id}`

`GET /evidence/{chain_id}` is no longer just a producer-side bridge in the abstract design; it is the concrete producer surface used to obtain the preferred v1 evidence package. `GET /chain-state/{chain_id}` and `GET /verify-chain/{chain_id}` remain internal operational inputs and should not be treated as the final external verifier contract or a normal operator workflow.

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

Operator output should keep provenance explicit:

- `replay.provenance=public` means the verifier recovered the required historical facts from public immutable replay material;
- `replay.provenance=mirrored` means public Rekor inclusion was present but verifier-critical DSSE payload fields had to be re-materialized from mirrored bundle content;
- `replay.provenance=degraded` means public materialization did not expose every verifier-critical historical fact;
- `replay.provenance=unsupported` means replay depended on process-local cache or another non-public reconstruction path.

The current CLI summarizes this explicitly as verification tiers:

- `public-only`
- `public+mirrored`
- `public+mirrored+attested`

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

## Operator Result Vocabulary

`tc-verify` should keep three result layers distinct:

- `summary`: top-level success, status, counts, and verification tier;
- `replay`: immutable replay entries plus provenance summary;
- `attested_head`: exported evidence binding status for the current head;
- `fallback`: live TruCon troubleshooting state when explicitly requested;
- `diagnostics`: a compact failure-oriented summary, including the first replay entry with a boundary, predecessor, or materialization problem.

- replay outcome: whether immutable-backend replay and signed predecessor continuity succeeded
- attested-head outcome: whether exported evidence validly binds the current public head to current TEE state
- profile outcome: whether build, publish, launch, or runtime semantics satisfy operator policy

For replayable records, operator-facing output should preserve the machine-readable predecessor vocabulary already used by immutable replay and TruCon verification:

- `origin`
- `proven`
- `missing`
- `ambiguous`
- `unverifiable`
- `lookup_failed`
- `decode_failed`

These predecessor verdicts should not be collapsed into generic profile failures. They explain why replay continuity did or did not hold before any application-level profile evaluation is applied.

For mixed replay regimes, operator output should also distinguish degraded replay from invalid replay:

- degraded replay: the verifier has incomplete predecessor-proof coverage across a regime boundary or pending-only state, so it cannot claim full replay proof for that segment
- invalid replay: the verifier found a concrete contradiction in signed predecessor continuity, digest recomputation, signer policy, or attested-head binding

This distinction matters operationally. Degraded replay means the evidence is incomplete or crosses a migration boundary; invalid replay means the available evidence contradicts the claimed chain state.

For the public Rekor rollout specifically:

- `boundary_status=degraded` means the verifier crossed a legacy-to-reservation migration boundary and can still observe the relevant immutable records, but it cannot claim one continuous reservation-backed predecessor proof across that whole segment.
- `boundary_status=invalid` means a chain had already entered the reservation-backed predecessor regime and later regressed back to incompatible legacy linkage, so operators should treat the replay result as contradictory rather than merely incomplete.

## Verification Profiles

The current implementation verifies flows independently rather than trying to compute one global workload verdict.

Implemented canonical profiles:

- `build`
- `publish`
- `launch`
- `docktap-runtime`

Shared verdict states:

- `verified`
- `warning`
- `incomplete`
- `failed`

The verifier keeps these profile results separate from structural replay and attested-head outcomes. A chain can replay successfully while one or more application profiles still return `warning`, `incomplete`, or `failed`.

Conversely, a profile may remain `warning` or `incomplete` even when replay predecessor continuity is fully `proven`, and a profile should not be allowed to mask a replay-level `missing`, `ambiguous`, `lookup_failed`, `decode_failed`, or otherwise invalid predecessor result.

### Build Profile

Required fields:

- `output_image_digest`
- `dockerfile_digest`
- `build_context_digest`
- `base_image_digests`
- `build_status`

Warning-only field:

- optional SBOM identity such as `sbom_digest`

Hard fail:

- missing `output_image_digest`
- build reported success but missing stable built-artifact identity
- malformed or missing required build-input identity

Warning:

- optional SBOM identity missing
- non-critical build metadata absent

### Publish Profile

Required fields:

- `pushed_subject_digest`
- `target_ref`
- `publish_status`

Hard fail:

- publish reported success but omitted `pushed_subject_digest`
- publish reported success but omitted `target_ref`
- bare success flag without stable pushed-subject identity

Warning:

- non-critical provenance metadata absent

### Launch Profile

The verifier uses `launch_id` as the authoritative v1 launch-attempt boundary and evaluates the latest workload-scoped launch attempt present in the chain.

Required fields:

- `launch_id`
- `workload_id`
- `image_digest`
- `launch_config_digest`
- `privileged`
- `network_mode`
- `mounts`
- `devices`
- `capabilities`

Conditionally required field:

- `instance_id` after a concrete container instance exists

Hard fail:

- missing `workload_id`
- missing `image_digest`
- missing `launch_config_digest`
- launch reported success but omitted required security projection fields
- create/start path failed for the selected `launch_id`
- missing `instance_id` after container scope exists

Warning:

- missing optional environment projection such as environment-key inventory or launch environment digest
- missing non-critical metadata that does not change launch risk

Special rule:

- a pre-create launch failure remains attributable by `launch_id` and does not fail solely because `instance_id` is absent

### Docktap Runtime Profile

Required fields for container-scoped operations:

- `operation_type`
- `operation_result`
- `workload_id`
- `instance_id`

Additionally required when the operation meaning depends on an image target:

- `image_ref` or `image_digest`

Optional correlation field:

- `launch_id` when the runtime event belongs to a REST-originated launch flow

Hard fail:

- missing workload identity for a workload-scoped runtime operation
- missing container identity for a container-scoped runtime operation
- successful runtime operation missing the audited target identity needed to understand what was acted on
- missing explicit `operation_result`

Warning:

- missing auxiliary metadata that does not change the audit meaning of the runtime action

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
- When should transitional TruCon-backed fallback verification be removed entirely from operator workflows?

## Related Documents

- [architecture.md](architecture.md) — trusted-log internal architecture and replay model
- [api.md](api.md) — Python and REST API contracts
- [README.md](README.md) — module overview and operational entry points
- [../architecture.md](../architecture.md) — top-level system architecture