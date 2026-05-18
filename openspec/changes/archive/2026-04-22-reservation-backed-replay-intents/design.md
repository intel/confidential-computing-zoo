## Context

The current trusted-log commit path is a one-shot flow: tc_api builds the payload, signs it, and posts the signed bundle to TruCon `/commit`. That flow works only while the signed payload does not need final sequencing inputs from TruCon. The new public replay contract changes that assumption because `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` must be correct before the DSSE bundle is signed, but TruCon currently determines those values only after it acquires the sequencer lock inside `/commit`.

That makes the earlier predecessor-replay design architecturally incomplete. The signer and the sequencer do not share a stable contract boundary. If tc_api signs before TruCon serializes chain access, the signed predecessor fields can be stale or wrong. If TruCon keeps assigning them after signature creation, they are not covered by the signature and therefore are not protocol truth.

This change introduces a durable reservation-backed commit-intent model so TruCon allocates the predecessor contract first, tc_api signs exactly that contract, and `/commit` validates and consumes the reserved intent rather than inventing ordering inputs at submit time. The change is cross-cutting because it affects tc_api signing, TruCon sequencing, SQLite persistence, baseline initialization, replay verification, CLI output, and the architecture and API documentation shipped under `docs/`.

## Goals / Non-Goals

**Goals:**
- Allocate replay-critical predecessor fields under the TruCon sequencer lock before tc_api signs a replayable event.
- Make the reservation durable so retries, process restarts, and expiry semantics are explicit rather than hidden in memory.
- Bind idempotency to the full `reserve -> sign -> commit` lifecycle.
- Use the same replay contract for Event Log 0, lazy workload bootstrap, and later records.
- Keep verifier truth in signed fields and treat Rekor lookup only as candidate discovery.
- Reflect the new architecture in `docs/architecture.md`, `docs/trusted-log/architecture.md`, and `docs/trusted-log/api.md` as part of delivery.

**Non-Goals:**
- This design does not introduce a new external storage backend beyond the existing SQLite state and immutable backend.
- This design does not attempt to support multiple simultaneously active reservations per chain in the initial rollout.
- This design does not redesign attested-head evidence formats beyond consuming the new replay semantics.
- This design does not make Rekor search complete, unique, or authoritative.

## Decisions

### Use a two-phase commit-intent protocol

TruCon will expose a reservation endpoint that returns an opaque `intent_token` plus the predecessor contract tc_api must sign: `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`. tc_api will construct the DSSE predicate from those values and submit the signed bundle back to `/commit` together with the `intent_token`.

Rationale:
- The sequencer, not the signer, owns the authoritative chain predecessor state.
- The signer must receive final immutable inputs before signature creation if those inputs are part of the public replay protocol.
- A two-phase protocol is the smallest architectural change that preserves TruCon as sequencer and tc_api as signer.

Alternatives considered:
- Keep one-shot `/commit` and let TruCon mutate unsigned predecessor fields after receipt: rejected because the replay contract would not be signed.
- Let tc_api guess predecessor fields from previous local state: rejected because it reintroduces races across workers and across transports.
- Move signing into TruCon: rejected because the design intentionally keeps business-context signing in tc_api and would collapse trust boundaries.

### Make reservations durable and single-use

Reservations will be stored in SQLite as `commit_intents` rows with status transitions such as `ACTIVE`, `CONSUMED`, `EXPIRED`, and `CANCELLED`. Each intent token is single-use. The initial implementation permits at most one `ACTIVE` intent per chain at a time.

Rationale:
- In-memory reservation state is not acceptable because process restarts would lose predecessor allocation truth while clients may still hold a token.
- Single-use tokens keep `/commit` validation simple and prevent replaying the same signed bundle into multiple queue rows.
- A single active reservation per chain avoids gap management, reservation supersession rules, and complex lock-free head advancement in the first version.

Alternatives considered:
- Allow multiple active reservations per chain: rejected for the initial change because it requires explicit gap handling, stale-intent invalidation, and more complex retry semantics.
- Keep reservation state only in memory and regenerate on restart: rejected because it breaks idempotent retries and makes crash recovery nondeterministic.

### Bind idempotency to the full intent lifecycle

The caller-facing idempotency key becomes the identifier for the whole lifecycle. A retry with the same `chain_id` and `idempotency_key` returns the existing active intent if the intent has not been consumed, or the original commit result if the intent has already produced a queue record.

Rationale:
- Callers retry the logical operation, not just the final enqueue step.
- Binding idempotency only to `/commit` is too late once reservation is a first-class step.
- Reusing the same contract on retry avoids generating multiple competing sequence reservations for one logical event.

Alternatives considered:
- Separate reserve-idempotency and commit-idempotency keys: rejected because it complicates client behavior and makes duplicate suppression harder to reason about.

### Treat reservation as sequencing allocation, not chain advancement

The sequencer lock allocates the next sequence slot and predecessor contract during reservation, but the chain head is not committed to `commit_queue` until `/commit` successfully validates the signed bundle and inserts the record. Because only one active intent is allowed per chain, later reservations for the same chain will block or fail with a conflict until the active intent is consumed or expires.

Rationale:
- The signed contract must be final before signing.
- The persisted queue must still represent only committed records.
- A single active intent per chain avoids gaps between reserved sequence numbers and committed sequence numbers.

Alternatives considered:
- Advance `chain_state` during reservation: rejected because it would make an uncommitted reservation indistinguishable from a committed head.
- Allow later reservations to skip over uncommitted ones: rejected because it creates observable gaps and complicates verification and crash recovery.

### Apply the same contract to Event Log 0 and workload bootstrap

Event Log 0 and lazy workload bootstrap will use the same reservation-backed predecessor contract as normal records. Baseline records therefore sign `sequence_num=1`, `prev_event_digest=null`, and `prev_lookup_hash=null` under a reserved intent rather than being inserted by TruCon as an unsigned special case.

Rationale:
- A single replay contract across the full chain reduces verifier branching and removes the last unsigned predecessor edge case.
- The prior lazy-baseline insertion model is incompatible with signed predecessor fields because TruCon cannot invent a signed baseline on behalf of tc_api.

Alternatives considered:
- Keep unsigned baseline insertion inside TruCon: rejected because it creates a protocol exception exactly at the chain origin.

### Make `/commit` a validation-and-consume endpoint

The final `/commit` call will validate that the signed bundle matches the reserved intent fields and only then insert the queue row, update chain state, and mark the intent consumed. Any mismatch between bundle content and reservation contract is a hard rejection.

Rationale:
- `/commit` must enforce that the queue reflects exactly what was reserved and signed.
- Explicit validation catches stale or tampered bundles before they affect local chain state.

Alternatives considered:
- Best-effort acceptance with warnings on mismatch: rejected because ordering inputs are part of the signed protocol contract.

### Keep verifier truth in signed predecessor fields

Immutable replay verification and TruCon `/verify-chain` will treat Rekor lookup as candidate discovery only. Verification will prove predecessor continuity using signed `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`, while old `prev_log_id` linkage becomes informational at most and leaves the protocol-critical path.

Rationale:
- Public replay must not depend on backend-assigned identifiers as protocol truth.
- The same rule should hold in immutable replay tooling, TruCon local verification, and CLI output.

Alternatives considered:
- Preserve `prev_log_id` verification as the non-TEE source of truth: rejected because it contradicts the new replay model and keeps backend identity in the protocol.

## Risks / Trade-offs

- [A stuck active intent can block a chain] -> Add explicit expiry timestamps, startup expiry recovery, and operator-visible diagnostics for active-intent conflicts.
- [Client retries may mix old tokens with new retries] -> Bind idempotency to the lifecycle and return the existing intent or existing commit result instead of minting competing reservations.
- [A process crash between reservation and commit can strand sequence allocation] -> Persist intent rows durably and expire or cancel them during recovery rather than advancing `chain_state` prematurely.
- [Single active intent per chain reduces concurrency] -> Accept the throughput trade-off in the initial rollout because it materially simplifies correctness and migration.
- [Baseline bootstrap now depends on the same reservation path] -> Cover Event Log 0 explicitly in specs and tests so chain origin does not remain a hidden special case.
- [Mixed old/new verification output can confuse operators] -> Update the CLI result model and the architecture/API docs in the same change, and keep field migrations explicit.

## Migration Plan

1. Add SQLite schema support for durable `commit_intents`, intent status transitions, replay metadata persistence, and startup expiry recovery.
2. Introduce the TruCon reserve endpoint and change `/commit` to consume an `intent_token` and validate the signed predecessor contract.
3. Update tc_api trusted-log flows to `reserve -> sign -> commit` for normal records and Event Log 0 initialization.
4. Replace old non-TEE predecessor verification logic with signed predecessor continuity in immutable replay, TruCon verification, and CLI rendering.
5. Update tests for reservation races, expiry, retry reuse, baseline bootstrap, replay traversal, and CLI output.
6. Update `docs/architecture.md`, `docs/trusted-log/architecture.md`, and `docs/trusted-log/api.md` so the documented control-plane flow matches the implementation.

Rollback strategy:
- Roll back before emitting new records under the reservation-backed contract, or gate the new contract behind a rollout flag until all producers and verifiers are updated.
- Because signed payload semantics change, mixed old/new records in the same chain should be treated as an explicit migration case rather than assumed to be transparently interchangeable.

## Open Questions

- Whether the reserve endpoint should block or return HTTP 409 when a chain already has an active intent is left to implementation detail, as long as the conflict is explicit and testable.
- Whether future versions should support multiple active reservations per chain remains open; this design intentionally defers that complexity.
- Whether attested-head exports should surface the new predecessor fields directly for operator inspection is still open and does not block this change.