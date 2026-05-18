## Status

Superseded by `reservation-backed-replay-intents`.

This design is no longer the active implementation path. The missing piece is architectural rather than editorial: it assumes signed predecessor fields can be produced safely inside the existing one-shot flow, but that is incompatible with TruCon assigning predecessor state only after sequencer serialization. The successor change moves that allocation into a durable reservation phase before signing.

## Context

The current public replay model mixes two different concerns into `prev_log_id`: finding a predecessor in Rekor and proving that the predecessor is the correct prior event in the chain. That model works only as long as the immutable backend's assigned identifier remains part of the public protocol and is available before callers need to reason about predecessor linkage.

This change replaces that backend-specific linkage with a protocol-level predecessor contract. The agreed model is a signed triplet carried in the public replay payload:

- `prev_event_digest`: the predecessor proof
- `sequence_num`: the predecessor position constraint
- `prev_lookup_hash`: the Rekor candidate-discovery key, defined as the predecessor DSSE `payloadHash(sha256)`

The codebase already distinguishes immutable-backend replay verification from TruCon RTMR verification, already stores `sequence_num` and `event_digest`, and already relies on Rekor bundle and DSSE semantics. The design therefore needs to reshape predecessor verification without reintroducing backend identity into the signed public contract.

## Goals / Non-Goals

**Goals:**
- Make public predecessor linkage independent of Rekor-assigned `log_id` values.
- Preserve practical replayability against public Rekor by using a lookup key that the current Rekor index can search.
- Separate candidate discovery from correctness so Rekor search incompleteness or non-uniqueness does not become protocol truth.
- Define explicit null-predecessor semantics for Event Log 0 so baseline replay fits the same contract as later records.
- Keep the verifier model testable and deterministic: candidate lookup, candidate filtering, and predecessor proof each have explicit inputs.

**Non-Goals:**
- This design does not eliminate reliance on Rekor for public history storage.
- This design does not guarantee that Rekor index search is complete or unique for all future deployments.
- This design does not introduce a new public indexing service beyond Rekor.
- This design does not redesign RTMR verification or attested-head quote binding beyond the replay fields they reference.

## Decisions

### Use a signed predecessor triplet instead of public `prev_log_id`

Each public replayable event will carry signed fields for `chain_id`, `sequence_num`, current `digest`, `prev_event_digest`, and `prev_lookup_hash`.

Rationale:
- `prev_log_id` is assigned by the immutable backend and therefore couples the public protocol to Rekor addressing.
- `sequence_num` and `prev_event_digest` are protocol-level values that TruCon and verifiers can reason about without knowing a Rekor UUID ahead of time.
- A signed triplet gives the verifier enough data to detect the correct predecessor even when lookup returns multiple candidates.

Alternatives considered:
- Keep `prev_log_id` in the signed payload: rejected because it preserves backend coupling and complicates asynchronous queue-first sequencing.
- Use only `prev_event_digest`: rejected because it proves correctness but does not provide a practical Rekor lookup key.

### Define `prev_lookup_hash` as predecessor `payloadHash(sha256)`

`prev_lookup_hash` is the predecessor DSSE payload hash as exposed by Rekor entry types that support payload-hash indexing.

Rationale:
- Public Rekor `/api/v1/index/retrieve` currently accepts `sha1`, `sha256`, and `sha512`, but recent DSSE entries are practically searchable by `payloadHash(sha256)`.
- `payloadHash` is more stable than whole-envelope hashes because it is tied to the DSSE payload rather than signature packaging details.
- `sha256` is sufficient because it is used only for candidate discovery; correctness is still enforced by `prev_event_digest` and `sequence_num`.

Alternatives considered:
- `sha512` payload hashes: rejected because they do not unlock a new capability, are not the naturally observed DSSE search path in current Rekor usage, and add protocol bulk without improving replay correctness.
- Envelope hash: rejected because envelope encoding and signature packaging make it a less stable lookup target.
- Subject digest reuse: rejected because the current project-level `event_digest` is `sha384` and is not directly accepted by Rekor `index/retrieve`.

### Treat Rekor search as candidate discovery only

The verifier algorithm is:
1. Query Rekor candidates with `prev_lookup_hash`.
2. Filter by matching `chain_id`.
3. Filter by `sequence_num == current.sequence_num - 1`.
4. Recompute each candidate's `event_digest`.
5. Require a candidate whose recomputed digest equals `prev_event_digest`.

Rationale:
- Rekor search may be incomplete or may return multiple entries for the same hash.
- The protocol must remain correct even if lookup is non-unique.
- Separating discovery from proof keeps correctness in signed chain fields rather than external index behavior.

Alternatives considered:
- Assume lookup hash uniqueness and accept the sole hit: rejected because it turns an operational property of Rekor search into a protocol assumption.

### Represent Event Log 0 with explicit null predecessor fields

Baseline records use the same public replay schema as later records, but with:
- `sequence_num = 1`
- `prev_event_digest = null`
- `prev_lookup_hash = null`

Rationale:
- This preserves one predecessor model across the whole chain.
- Explicit null semantics are easier to validate than field absence.
- Event Log 0 remains the epoch anchor while still participating in the same signed replay contract.

Alternatives considered:
- Omit predecessor fields from Event Log 0: rejected because it introduces a schema fork and complicates verifier logic.

## Risks / Trade-offs

- [Rekor `index/retrieve` is experimental / deprecated] → Treat it as best-effort candidate discovery only and keep correctness in signed fields.
- [Lookup may return multiple candidates] → Require verifier filtering by `chain_id`, `sequence_num`, and recomputed `prev_event_digest`.
- [Lookup may fail to return a valid predecessor even when it exists] → Report replay failure explicitly; do not claim protocol invalidity based solely on index incompleteness.
- [DSSE payload-hash semantics are tied to current Rekor entry handling] → Encode the exact `payloadHash(sha256)` contract in specs and tests so future changes are visible.
- [Existing non-TEE `prev_log_id` verification logic becomes obsolete] → Replace it with the signed predecessor contract and remove public reliance on `prev_log_id` from verification rules.

## Migration Plan

1. Update public DSSE predicate construction to emit the new predecessor fields.
2. Update immutable replay verification to perform candidate discovery through `prev_lookup_hash` and proof through `prev_event_digest` plus `sequence_num`.
3. Update TruCon chain verification to validate predecessor continuity with the new replay fields instead of non-TEE `prev_log_id` linkage checks.
4. Update Event Log 0 generation to include explicit null predecessor fields.
5. Extend public Rekor integration tests and verification documentation to cover lookup, candidate filtering, and baseline null-predecessor semantics.

Rollback strategy:
- Because this changes signed public replay semantics, mixed chains should not be treated as transparently equivalent. Rollback means reverting to the prior replay contract before emitting new records under the changed format, or treating the new format as a gated protocol revision during rollout.

## Open Questions

- Whether attested-head evidence should eventually expose `head_lookup_hash` alongside `head_event_digest` for operator tooling remains open, but it is not required for this change.
- Whether verifier implementations should maintain a local `(chain_id, sequence_num)` cache for performance is left to implementation and does not change the protocol contract.