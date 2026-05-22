## Context

TruCon currently wires one immutable-log adapter during application startup through a single `TC_IMMUTABLE_BACKEND` value and passes that adapter into `SubmitDaemon`. That model is sufficient for today's Rekor-only operation, but it cannot express the next rollout step where Rekor remains the authoritative backend while an on-chain backend is introduced behind a guarded fanout skeleton.

The current on-chain package is intentionally a placeholder that raises `NotImplementedError`. This change therefore needs to add the configuration and composition surfaces for multi-backend operation without accidentally turning on a broken `rekor,onchain` deployment path.

The implementation surface is cross-cutting but still localized: TruCon config parsing, immutable adapter loading, and submit-daemon submission semantics. The verification and replay paths should remain anchored to one configured read backend in this phase.

## Goals / Non-Goals

**Goals:**
- Introduce a configuration model that can describe one or more enabled immutable write backends at TruCon startup.
- Add a composite immutable adapter skeleton that fans out submissions while preserving one primary/read backend for existing traversal and lookup flows.
- Define guarded startup behavior so unsupported combinations such as `rekor,onchain` fail fast while on-chain remains unimplemented.
- Keep single-backend operation straightforward for `rekor`-only and `onchain`-only startup modes.
- Prepare future multi-backend confirmation behavior with explicit write-policy semantics.

**Non-Goals:**
- Implementing real on-chain submission, traversal, or verification.
- Redesigning immutable replay to merge results from multiple backends.
- Adding durable per-backend record status tables in this first step.
- Changing the DSSE payload format or TruCon reservation protocol.

## Decisions

### 1. Represent immutable backends as a configured write set, not a single selector
TruCon will move from a single backend selector to a backend-set configuration such as `rekor`, `onchain`, or `rekor,onchain`. A separate primary/read backend setting keeps read-oriented code deterministic.

Why:
- Submission fanout and replay authority are different concerns.
- Existing verification and lookup code assumes one authoritative backend.
- Operators need a clean path to express future dual-write without rewriting the daemon around backend lists.

Alternative considered:
- Reusing a single `TC_IMMUTABLE_BACKEND` string and inventing special values such as `rekor+onchain`. Rejected because it scales poorly and makes read/write semantics ambiguous.

### 2. Keep `SubmitDaemon` bound to one `ImmutableLogAdapter` instance by introducing a composite adapter
Instead of teaching the daemon about multiple backends directly, TruCon will construct either a concrete backend adapter or a composite/fanout adapter that still implements `ImmutableLogAdapter`.

Why:
- Preserves the current daemon shape and minimizes invasive changes.
- Keeps backend fanout logic behind the immutable adapter boundary.
- Allows future extension to more than two backends with one composition point.

Alternative considered:
- Passing `list[ImmutableLogAdapter]` into the daemon and branching inside `_submit_record()`. Rejected because it leaks backend orchestration into the daemon and duplicates selection policy there.

### 3. In phase one, multi-backend writes use a primary/read backend as the authoritative confirmation source
The composite adapter will return the primary backend's `(log_id, status, receipt)` contract to existing callers while retaining backend-specific results internally for logging and future state expansion.

Why:
- Existing confirmation and replay logic already centers on one backend identity.
- Rekor is the only implemented production backend today.
- This avoids an immediate database schema change while still establishing fanout wiring.

Alternative considered:
- Requiring all configured backends to succeed before a record becomes confirmed. Rejected for phase one because it would couple production success to an unfinished backend and force broader state-model changes.

### 4. Unsupported multi-backend combinations fail during startup
If startup configuration asks for `rekor,onchain` while the on-chain adapter is still a placeholder, TruCon will fail fast with a clear configuration error before it starts serving traffic.

Why:
- Prevents operators from believing dual-write is active when one sink cannot submit.
- Matches the user's current requirement: expose the interface and composition skeleton first, but do not enable the unfinished combined mode.

Alternative considered:
- Allowing startup but degrading silently to Rekor-only. Rejected because it hides configuration intent and would make later rollout debugging harder.

### 5. No per-backend persistent state in this change
Backend-specific outcomes will be logged and surfaced through the composite adapter contract, but database-level backend status tracking is deferred.

Why:
- The immediate goal is configuration and composition scaffolding.
- The existing queue/confirmation model can stay intact if the primary backend remains authoritative.

Alternative considered:
- Adding a `record_backend_status` table now. Rejected as useful later but unnecessary for establishing the first guarded fanout slice.

## Risks / Trade-offs

- [Primary-backend confirmation masks secondary-backend failures] → Log backend-specific results explicitly and keep write-policy configuration explicit so later phases can tighten behavior.
- [Future on-chain rollout may need interface changes beyond the current three-tuple return contract] → Keep the composite adapter internal and evolve returned metadata in a controlled follow-up if needed.
- [Configuration compatibility drift between old and new environment variables] → Define one canonical backend-set interface and treat any legacy selector as a temporary compatibility alias only.
- [Operators may expect dual-read or merged verification once dual-write configuration exists] → Keep read-backend behavior explicit in the spec and documentation, and mark merged replay as out of scope.
