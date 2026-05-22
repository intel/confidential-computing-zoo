## Context

The current trusted-log flow already separates three verification surfaces: public immutable-log replay, current-head attested evidence, and local bundle-derived convenience state. The gap is that public Rekor entries for DSSE submissions do not reliably preserve enough payload material to reconstruct predecessor contracts after cache is cleared, while attested-head evidence intentionally does not carry historical replay proof. This change introduces a dedicated materialization layer for newly written nodes without turning that layer into a new proof authority.

## Goals / Non-Goals

**Goals:**
- Restore full replayable bundle material for newly written nodes without weakening Rekor's authority for public inclusion proof.
- Anchor mirror lookup on a stable content identity that already participates in replay semantics: `payload_hash`.
- Keep mirror publication outside the authoritative commit path so Rekor confirmation remains the only trust-critical commit gate.
- Expose verification tiers that distinguish public-only replay, mirrored replay, and mirrored replay plus attested current-head binding.
- Prove feasibility early with a focused OCI test harness before full implementation work expands.

**Non-Goals:**
- Backfilling or reprocessing historical chains created before mirror publication exists.
- Replacing Rekor with OCI storage as the authority for inclusion or historical proof.
- Embedding mirror locator data into the signed DSSE payload or attested-head evidence package.
- Expanding the attested-head evidence contract into a historical replay carrier.

## Decisions

### Decision: OCI artifact storage is the first mirror backend

The first implementation uses OCI artifact storage and mirrors the original `bundle.json` rather than a derived replay-only representation.

Rationale:
- The system already signs, transmits, and parses `bundle.json` directly.
- Mirroring the original object avoids inventing a new authority-bearing format.
- OCI registries give a practical distribution mechanism without changing replay semantics.

Alternatives considered:
- Object storage or filesystem export first: rejected because OCI gives a clearer distribution and retrieval model for a multi-environment verifier.
- Storing only a normalized replay view: rejected because it would turn a derived representation into a trust-sensitive artifact.

### Decision: `payload_hash` is the primary lookup anchor

Mirror resolution is content-addressed. `payload_hash` is the primary lookup key, while `chain_id`, `sequence_num`, `event_digest`, and `rekor_log_id` are secondary indexes or annotations.

Rationale:
- `prev_lookup_hash` already carries the verifier-facing predecessor discovery anchor.
- Content-addressed lookup is more stable than human-oriented names or mutable tags.
- Resolver indirection allows registry layout changes without changing signed protocol semantics.

Alternatives considered:
- Naming by `chain_id` and `sequence_num`: rejected because those are deployment-facing labels, not the strongest cross-system identity.
- Embedding an OCI reference in the signed payload: rejected because transport location should not become part of the signed replay contract.

### Decision: Mirror publish happens asynchronously after Rekor confirmation

Bundle publication to the mirror happens only after Rekor confirms the log entry. A durable queue or equivalent retryable publisher bridges the authoritative commit path and the mirror publish path.

Rationale:
- Rekor remains the only trust-critical commit gate.
- Mirror failures can be retried independently instead of complicating the commit transaction.
- The system can truthfully represent a temporary `public-only` window while mirrored material is still pending.

Alternatives considered:
- Synchronous dual submission to Rekor and OCI: rejected because it couples the authoritative path to a second external dependency and creates avoidable rollback ambiguity.
- External batch replication only: rejected for phase 1 because it hides publication ownership and makes availability windows harder to reason about.

### Decision: Verifier policy supplies mirror configuration and result tiering

Mirror base location and strictness come from verifier policy or verification profiles, not from signed payload data. Verification outcomes are reported as `public-only`, `public+mirrored`, or `public+mirrored+attested`.

Rationale:
- Transport configuration belongs in verifier policy, not in the signed protocol payload.
- Result tiers keep provenance explicit for operators.
- Mirror-required versus mirror-optional behavior can evolve without mutating the signed replay contract.

Alternatives considered:
- Hard-coded mirror configuration: rejected because deployment topology is environment-specific.
- Hiding mirror provenance behind a generic success state: rejected because it would blur the public-proof boundary again.

### Decision: Feasibility spike is a first-class deliverable

Before full rollout, the change includes a focused test program or harness that proves OCI publication and retrieval for mirrored bundles and verifies policy behavior when mirrored content is missing or delayed.

Rationale:
- The main uncertainty is operational feasibility and resolver behavior, not the abstract trust model.
- A spike prevents over-design before the registry interaction is proven end-to-end.

Alternatives considered:
- Proceed directly to full implementation: rejected because registry mechanics and retrieval semantics need proof first.

## Risks / Trade-offs

- [Risk] Mirror configuration diverges across verifier environments and produces different materialization outcomes. → Mitigation: keep `payload_hash` as the protocol anchor, treat mirror location as policy data, and surface result tiers explicitly.
- [Risk] Operators mistake mirrored retrieval for authority rather than materialization. → Mitigation: keep specs and CLI wording explicit that Rekor remains the inclusion authority and mirror only restores signed content.
- [Risk] Asynchronous publication creates a temporary window where a confirmed record is not yet mirrored. → Mitigation: model that state explicitly as `public-only` and provide retryable publish status rather than pretending the mirror is immediately complete.
- [Risk] OCI naming conventions ossify around an early implementation detail. → Mitigation: define a resolver contract around `payload_hash` instead of making raw registry path conventions part of the protocol.

## Migration Plan

1. Add proposal-backed specs and design that define mirror publication, lookup, and verifier-tier behavior for newly written nodes only.
2. Build the OCI feasibility harness and confirm intact publication, retrieval, and policy-driven missing-content behavior.
3. Add asynchronous post-confirmation mirror publication for new replayable bundles.
4. Extend immutable replay verification and CLI reporting to consume mirrored material and emit tiered results.
5. Roll out mirror-aware verification profiles once the OCI path is proven stable.

Rollback strategy: disable mirror publication and mirror-required policy paths while retaining Rekor-only verification if OCI publication or retrieval proves unstable.

## Open Questions

- Should the first OCI implementation use a lightweight side manifest or rely only on registry annotations alongside the original `bundle.json`?
- Which verification profiles, if any, should default to mirror-required versus mirror-optional once the feature leaves the spike phase?
- Should mirror publish status be exposed through TruCon state APIs, or remain an internal operational concern until a later change?