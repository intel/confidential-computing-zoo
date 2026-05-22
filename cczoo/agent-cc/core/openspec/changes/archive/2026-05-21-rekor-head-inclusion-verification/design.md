## Context

Current verification already combines immutable-backend replay, signed predecessor continuity, owner or delegation checks, and attested-head evidence matching. That stack proves application-level history continuity for the accepted head, but it does not yet require the verifier to prove that the accepted `head_log_id` was integrated into a signed Rekor tree state. The change therefore needs to extend existing verification surfaces rather than introducing a separate verifier product: the Rekor adapter must expose proof material, `TrustedLogAPI.verify_record()` must evaluate and normalize that material, and `tc-verify` must report the result without overstating degraded states as successful public-log verification.

The main constraint is scope control. This first change is intentionally smaller than a full transparency-log audit system: it targets the accepted head entry only, allows an explicit bootstrap trust source for the first trusted checkpoint, and avoids claiming cross-time anti-fork guarantees that would require stored historical checkpoints and consistency proofs.

## Goals / Non-Goals

**Goals:**
- Prove that the accepted Rekor `head_log_id` belongs to a signed Rekor tree state rather than relying on entry readback alone.
- Validate the signed checkpoint or equivalent signed tree head that anchors the accepted head entry's inclusion proof.
- Thread head-entry log verification into shared verifier result models and CLI output as a dimension separate from replay continuity and attested-head evidence.
- Preserve explicit degraded and troubleshooting-only states when proof or checkpoint material is unavailable.
- Keep the design small enough to land as an incremental extension to the existing replay verifier.

**Non-Goals:**
- Verifying inclusion proofs for every historical replay entry in the first iteration.
- Persisting historical checkpoints and proving consistency across time.
- Gossip, witness co-signing, or any multi-source checkpoint corroboration workflow.
- Abstracting the implementation into a generic transparency-log provider model beyond Rekor.
- Treating missing proof material as equivalent to cryptographic proof failure in every mode.

## Decisions

### Decision: Verify only the accepted head entry in the MVP
The verifier will require inclusion-proof validation for the accepted `head_log_id`, not for every replayed historical entry.

Rationale:
- This closes the most immediate trust gap around the record that the verifier ultimately accepts as the current public head.
- It avoids multiplying network calls, result-shape complexity, and failure semantics across the entire replayed history in the first version.
- It keeps the change aligned with the current verifier architecture, where replay establishes history continuity and a smaller set of summary outcomes is surfaced to the CLI.

Alternatives considered:
- Verify all confirmed replay entries immediately: stronger, but too large for the MVP and likely to complicate degraded-state handling.
- Keep entry readback only: rejected because it does not actually verify transparency-log integration.

### Decision: Extend existing Rekor adapter and shared verification result structures
The Rekor adapter will be extended to retrieve head-entry proof material, and `TrustedLogAPI.verify_record()` will normalize a dedicated log-verification section alongside existing replay results.

Rationale:
- The adapter already owns Rekor retrieval details and is the natural place to encapsulate entry, proof, and checkpoint fetch mechanics.
- `TrustedLogAPI.verify_record()` already serves as the structured immutable-backend verification surface consumed by the CLI.
- Reusing the current result pipeline avoids creating a second verifier contract with conflicting semantics.

Alternatives considered:
- Add a separate CLI-only inclusion verifier: rejected because it would fork verification logic and result semantics.
- Put proof handling entirely in the CLI: rejected because it would bypass shared policy and shared result normalization.

### Decision: Use explicit bootstrap trust for the first signed checkpoint
The first version will allow a configured or explicitly supplied initial trust source for checkpoint validation.

Rationale:
- Inclusion proof verification needs a trust anchor for the signed tree head; the system cannot derive that purely from the current entry.
- A controlled bootstrap model is sufficient for the MVP and matches the intended non-goal of not claiming historical anti-fork guarantees yet.
- This keeps the initial rollout operationally manageable while leaving room for later checkpoint persistence and consistency-proof work.

Alternatives considered:
- Require historical checkpoint persistence immediately: rejected as too large for the MVP.
- Treat Rekor's latest returned checkpoint as self-authenticating: rejected because it collapses trust bootstrap into unaudited server response handling.

### Decision: Separate degraded proof unavailability from proof failure
Verifier outputs will distinguish at least successful head inclusion, degraded log verification due to unavailable proof material, and hard failure due to invalid proof or invalid checkpoint signature.

Rationale:
- Existing verification flows already distinguish degraded replay from invalid replay and should preserve that discipline for log verification.
- Operators need to know whether they hit an availability gap or a cryptographic contradiction.
- This avoids overstating public-log assurance while still allowing troubleshooting and partial verification workflows.

Alternatives considered:
- Fail closed on any proof material absence: simpler, but too disruptive for current operational troubleshooting and rollout.
- Collapse unavailable and invalid into a single state: rejected because it weakens operator diagnostics.

## Risks / Trade-offs

- Bootstrap trust may be misunderstood as full anti-fork protection → The proposal and CLI output must state clearly that the MVP validates current head inclusion only and does not prove cross-time consistency.
- Rekor proof retrieval shape may not align cleanly with current adapter usage → Keep proof fetching encapsulated in the adapter so the shared verifier only consumes normalized proof facts.
- Added verification dimensions may confuse downstream JSON consumers → Add explicit machine-readable fields instead of overloading existing replay status or tier fields.
- Degraded semantics could be overused and mask operational issues → Surface degraded states prominently in both JSON and human-readable output and reserve success for completed proof validation.

## Migration Plan

1. Introduce adapter support for retrieving normalized head-entry inclusion and checkpoint material.
2. Extend shared verification results to carry log-verification status, checkpoint validation status, and degraded reasons.
3. Update `tc-verify` JSON and terminal rendering to report the new dimension separately from replay and attested-head evidence.
4. Roll out the new status fields first in evidence-backed verification paths, while keeping troubleshooting-only paths explicit when proof material is unavailable.
5. Leave checkpoint persistence and consistency-proof enforcement for a later follow-on change.

Rollback strategy:
- If proof retrieval or checkpoint validation causes interoperability issues, revert to the prior verifier contract while preserving any additive result fields as optional until the follow-on design is ready.

## Open Questions

- What is the exact checkpoint trust source for the first verified run: static configuration, shipped key material, or operator-supplied trust root?
- Does the chosen Rekor client path expose inclusion proof and checkpoint material directly, or will the adapter need raw API calls for normalization?
- Should the first version mark missing proof material as `degraded` in evidence-backed mode and `troubleshooting-only` in live mode, or should that distinction be driven only by invocation mode?