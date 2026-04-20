## Context

The repository now treats per-workload chains as first-class verification targets, but only the startup-initialized `default` chain receives an explicit Event Log 0 baseline today. New non-`default` chains are created implicitly on the first `/commit`, so their first persisted record is a business or runtime event instead of a baseline anchor.

That mismatch now matters more than it did when only the `default` chain was verification-relevant. TruCon already owns chain sequencing, chain-state mutation, and concurrency control behind `_sequencer_lock`, and both REST and Docktap already rely on a simple `/commit` contract. The design therefore needs to make workload-chain origin semantics consistent without pushing initialization orchestration back to callers.

## Goals / Non-Goals

**Goals:**
- Ensure every first-class non-`default` workload chain begins with an explicit Event Log 0 baseline.
- Keep workload-chain baseline semantics aligned with the existing `default` chain behavior and terminology.
- Preserve the current caller contract for REST and Docktap so first commits still use `/commit` only.
- Make lazy workload-chain baseline creation race-safe under concurrent first commits from different callers.
- Make verification fail explicitly when a non-`default` chain does not begin with Event Log 0.

**Non-Goals:**
- Changing the role or continued existence of the `default` chain.
- Introducing an external pre-initialization step for REST or Docktap callers.
- Redefining the current `sequence_num >= 1` contract or remapping Event Log 0 to `sequence_num = 0`.
- Expanding the scope to on-chain backends, worker-leasing, or other open architecture questions outside workload-chain baseline semantics.

## Decisions

### 1. TruCon performs lazy baseline creation for unknown non-default chains

The first `/commit` received for an unknown non-`default` `chain_id` will trigger implicit baseline creation inside TruCon while holding `_sequencer_lock`.

Rationale:
- TruCon already owns chain existence, `sequence_num` allocation, and chain-state mutation.
- Keeping baseline creation inside TruCon avoids pushing a multi-step init protocol into REST and Docktap.
- The existing lock provides the right place to serialize first-commit races without introducing caller-visible coordination.

Alternatives considered:
- Explicit caller-side pre-initialization: rejected because it leaks chain bootstrap semantics into REST and Docktap and creates more race windows.
- Background or asynchronous baseline creation after first business commit: rejected because it would allow workload chains to begin without a baseline anchor.

### 2. Workload-chain baseline semantics reuse the default-chain model

Lazy-created workload baselines will reuse the current Event Log 0 fact model and ordering semantics already used for the `default` chain.

Concretely:
- Event Log 0 remains the baseline record name.
- The baseline record keeps `sequence_num = 1`.
- The first business or runtime event on that chain gets `sequence_num = 2`.
- Subsequent commits are not blocked while the baseline record is still pending immutable-backend confirmation.

Rationale:
- This keeps verifier expectations uniform across chain types.
- It avoids changing current sequence-number assumptions in evidence export, chain verification, and queue semantics.
- Multiple workload chains in the same CVM lifetime may record the same platform baseline facts while remaining distinct chains because the chain identity is still carried by `chain_id`.

Alternatives considered:
- Starting the first business event at `sequence_num = 0`: rejected because current code and evidence contracts already assume `sequence_num >= 1`.
- Creating workload-specific baseline content: rejected because current Event Log 0 is a platform baseline anchor, not a workload-specific environment snapshot.

### 3. First-commit races are resolved entirely inside TruCon

There is no caller-visible "baseline creator" role. When concurrent first commits arrive for the same new workload chain, the request that first acquires `_sequencer_lock` creates the baseline and then persists its own event. Later requests see an existing chain and proceed as normal commits.

Expected behavior:
- First request for new workload chain: baseline inserted as `sequence_num = 1`, business event inserted as `sequence_num = 2`, response returns the business event's commit result.
- Second concurrent request: normal commit path, receiving `sequence_num = 3` (or higher depending on contention).

Rationale:
- This keeps `/commit` responses stable and avoids surfacing `409 already initialized` control-plane behavior to normal business callers.
- It uses the sequencing service to solve a sequencing problem.

Alternatives considered:
- Returning a special response indicating that the caller created the baseline: rejected as unnecessary coupling to an internal bootstrap detail.
- Making callers retry after a 409/425-style initialization response: rejected because it complicates every producer path.

### 4. Baseline creation failure rejects the triggering first business event

If TruCon cannot create the required baseline for a new non-`default` chain, it rejects the first `/commit` instead of accepting a business/runtime event onto a chain without a baseline anchor.

Rationale:
- Once workload chains are treated as first-class verifiable chains, accepting a first business event without Event Log 0 would violate the chain-origin invariant at the moment the chain is born.
- This keeps the failure mode explicit and avoids partially initialized chains.

Alternatives considered:
- Accepting the business event and trying to repair the baseline later: rejected because it creates ambiguous chain origin and makes verification dependent on post hoc repair.

### 5. Verification upgrades baseline presence from convention to invariant

Both TruCon chain verification and `tc-verify` will explicitly require non-`default` chains to begin with Event Log 0. A non-`default` chain whose first record is not a baseline record is structurally invalid.

Rationale:
- Without verifier enforcement, lazy baseline creation would remain a producer-side best effort rather than a verifiable contract.
- The attested-head design already treats Event Log 0 as the baseline anchor, so workload chains should meet the same prerequisite.

Alternatives considered:
- Reporting missing baseline as `incomplete`: rejected because this is a structural contract violation, not merely missing evidence.

## Risks / Trade-offs

- [Risk] `/commit` becomes a compound path for first workload commits rather than a single-row insert.
  Mitigation: keep the extra work fully internal to TruCon and under the existing sequencer lock.

- [Risk] The first commit to a new workload chain will be slightly more expensive and can fail for baseline-specific reasons.
  Mitigation: limit the added behavior to unknown non-`default` chains only and keep failure explicit.

- [Risk] Multiple workload chains in one CVM lifecycle may record equivalent platform baseline facts, which can look repetitive.
  Mitigation: document that baseline facts may repeat across chains while still serving as distinct chain-local origin records.

- [Risk] Verification becomes stricter and may mark pre-change workload chains or malformed test fixtures as invalid.
  Mitigation: scope the invariant clearly in specs and update tests/fixtures alongside the change.

## Migration Plan

1. Extend TruCon's first-commit logic so unknown non-`default` chains auto-create Event Log 0 before persisting the triggering business event.
2. Preserve the existing `default` startup initialization flow; do not route it through the lazy path.
3. Update TruCon verification and `tc-verify` replay logic to require Event Log 0 at the head of non-`default` chains.
4. Refresh architecture and verification docs to describe lazy workload baseline creation and first-commit sequencing.
5. Update regression tests for concurrent first commits, first-event sequencing, and verification failure on missing workload-chain baseline.

Rollback strategy:
- Revert the lazy baseline behavior and verification invariant together. Rolling back only one side would reintroduce a producer/verifier mismatch.

## Open Questions

No blocking design questions remain for this proposal. Longer-term items such as on-chain backends, worker ownership, and future default/workload role evolution remain outside this change.