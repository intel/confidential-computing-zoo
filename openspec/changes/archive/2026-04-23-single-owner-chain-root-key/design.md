## Context

TruCon currently uses Event Log 0 as a structural baseline anchor and uses reservation-backed predecessor contracts to preserve replay continuity. The baseline payload stores a `pub_key`, but the existing model does not treat that key as a durable chain authority. Existing attested-head evidence intentionally binds only the latest confirmed public head and explicitly avoids taking over Event Log 0 bootstrap semantics.

The proposed change introduces a single-owner model: Event Log 0 declares one long-lived chain owner public key, TEE-backed baseline attestation proves that the declaration originated from the approved initialization context, and later replayable records must be authorized by the corresponding private key. This is cross-cutting because it changes initialization semantics, commit admission, persistence, verification, and operator-facing provenance.

## Goals / Non-Goals

**Goals:**
- Establish Event Log 0 `pub_key` as the single long-term owner authority for a chain.
- Bind the declared owner public key to baseline initialization context using a dedicated TEE-backed attestation contract.
- Require later replayable commits to prove authorization by that owner key in addition to predecessor continuity.
- Keep current-head attested evidence and baseline owner attestation as separate trust contracts.
- Make verification results distinguish owner-authorization failures from predecessor-continuity failures.

**Non-Goals:**
- Support multi-owner, delegation, or key-rotation workflows in this change.
- Replace internal service authentication with owner-key authorization.
- Reuse the attested-head evidence envelope for baseline owner attestation.
- Define long-term secure storage, migration, or escrow policy for the owner private key beyond the immediate single-owner model.

## Decisions

### 1. Event Log 0 `pub_key` becomes a durable owner key, not an ephemeral bootstrap field
The owner public key declared at Event Log 0 will define the sole chain-local writer authority for later replayable records. This gives the chain an intrinsic owner identity instead of relying only on trusted transport and predecessor contracts.

Alternatives considered:
- Keep `pub_key` informational only: rejected because it adds no admission semantics.
- Continue using short-lived Sigstore/Fulcio identities for every write: rejected because it does not define a stable chain-local owner.

### 2. Baseline owner attestation is a new contract, separate from attested-head evidence
The system will introduce a dedicated baseline owner attestation capability. Its quote binding covers the Event Log 0 initialization context, including `chain_id`, `sequence_num=1`, baseline platform measurements, and the declared owner public key. The full owner public key remains in the baseline payload; the quote binds a canonical digest over those fields rather than embedding the full PEM verbatim as the trust-critical report-data payload.

Alternatives considered:
- Extend attested-head evidence to carry baseline owner material: rejected because existing evidence intentionally excludes historical bootstrap facts.
- Publish owner attestation only in process-local state: rejected because verifiers need a durable replayable contract.

### 3. Reservation-backed commits require owner-key authorization in addition to predecessor matching
Commit admission will remain two-layered. The existing predecessor contract proves that a record links to the correct prior head; the new owner signature proves that the caller is authorized by the chain owner declared at Event Log 0. TruCon will verify both before queue insertion.

Alternatives considered:
- Replace predecessor contracts with owner signatures only: rejected because ownership does not prove adjacency.
- Rely on internal service authentication only: rejected because transport identity is weaker than chain-local ownership semantics.

### 4. Verification reports owner authorization as a distinct proof dimension
Historical replay verification will add machine-readable owner-authorization status alongside existing predecessor and RTMR checks. Operators need to distinguish “record linked correctly but was not owner-authorized” from “record failed predecessor continuity” and from “record is pending so owner proof is not yet replayable.”

Alternatives considered:
- Fold owner failures into predecessor errors: rejected because it obscures the new trust model.
- Verify owner authorization only at admission time: rejected because replay verification must remain independently auditable.

## Risks / Trade-offs

- [Long-lived owner private key increases compromise blast radius] → Mitigation: scope this change to a single-owner model only, document the security assumption clearly, and leave rotation/delegation for a later change.
- [TEE attestation may prove baseline declaration but not ongoing runtime custody of the private key] → Mitigation: state explicitly that baseline attestation bootstraps trust while later owner signatures provide ongoing authorization.
- [Admission changes may break existing producers that only sign predecessor contracts] → Mitigation: mark the new owner-authorization requirement as a spec-level change and phase implementation behind updated client flows.
- [Verifier complexity increases] → Mitigation: keep owner verification machine-readable and separate from predecessor logic rather than interleaving both into ambiguous status values.

## Migration Plan

1. Introduce the baseline owner attestation contract and persist owner-attestation material on Event Log 0.
2. Update initialization flows so new chains declare a durable owner key and publish the corresponding attestation.
3. Extend commit request and persistence contracts to carry owner authorization for reservation-backed replayable writes.
4. Update TruCon verification and CLI/reporting so owner-authorization state is visible.
5. Roll out updated producers before enabling strict owner-key enforcement for all replayable writes.

Rollback strategy:
- If strict owner authorization cannot be rolled out safely, preserve the recorded owner-attestation data but gate admission enforcement until clients are updated.

## Open Questions

- Where the single long-term owner private key lives operationally after bootstrap remains an implementation decision outside this change's normative scope.
- Whether owner authorization should sign the entire DSSE payload, a canonical subset, or an explicit authorization envelope still needs a concrete format choice during implementation.
- Whether verification should require public replay of owner authorization for pending local records or treat them as temporarily unverifiable needs a final UX choice.