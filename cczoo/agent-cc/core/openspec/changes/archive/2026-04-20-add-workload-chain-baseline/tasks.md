## 1. TruCon Baseline Bootstrap Path

- [x] 1.1 Extend the TruCon `/commit` path to detect unknown non-`default` chains and create Event Log 0 before inserting the triggering business or runtime record.
- [x] 1.2 Reuse the existing baseline payload model and ordering semantics so the lazy-created baseline receives `sequence_num=1` and the first triggering business event receives `sequence_num=2`.
- [x] 1.3 Ensure the lazy baseline path runs entirely under the sequencer lock and rejects the triggering first commit if baseline creation cannot complete.
- [x] 1.4 Preserve the current startup initialization path for the `default` chain without routing it through the lazy workload-chain bootstrap logic.

## 2. Verification Invariants

- [x] 2.1 Update TruCon chain verification to treat Event Log 0 as a required first record for non-`default` chains and surface a structural failure when it is missing.
- [x] 2.2 Update `tc-verify` replay logic in both evidence-backed and live fallback modes to fail non-`default` chains whose first replayed record is not Event Log 0.
- [x] 2.3 Confirm that pending workload-chain baselines still satisfy the origin requirement while continuing to count as pending immutable-backend records.

## 3. Regression Coverage

- [x] 3.1 Add TruCon tests for first workload commit lazy bootstrap, including baseline-first ordering and returned `sequence_num` values.
- [x] 3.2 Add concurrency tests covering a first-commit race between REST and Docktap for the same new workload chain.
- [x] 3.3 Add failure-path tests showing that baseline creation failure rejects the triggering first business event.
- [x] 3.4 Add verification tests for non-`default` chains with and without Event Log 0 in both TruCon verification and `tc-verify` replay flows.

## 4. Documentation And Task Overview Sync

- [x] 4.1 Update architecture and verification docs to describe lazy workload-chain baseline creation, first-event sequencing, and the shared Event Log 0 semantics across `default` and workload chains.
- [x] 4.2 Update `docs/overview_tasks.md` to reflect the implemented behavior and close `GAP-20` when code, tests, and docs are complete.

## 5. Validation

- [x] 5.1 Run targeted regression suites for chain initialization, TruCon verification, CLI verification, and workload-chain routing.
- [x] 5.2 Run the broader repository test suite required to confirm that default-chain initialization and existing producer flows still behave as before.