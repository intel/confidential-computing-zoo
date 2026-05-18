## Why

The TruCon sequencer currently uses only three lifecycle states (`PENDING`, `CONFIRMED`, `FAILED`). The architecture (§5.1) requires six states to distinguish between records being assembled, actively submitted, retryable failures, and terminal failures. Without granular states, the submit daemon cannot distinguish a retryable transient failure from a permanent one, the observability metrics (GAP-04) for `submit_latency` and `terminal_failure_count` lack proper semantic hooks, and operators have no visibility into whether a failed record can self-heal or requires intervention.

## What Changes

- **BREAKING**: `SubmitStatus` enum extended from 3 values (`PENDING`, `CONFIRMED`, `FAILED`) to 6 values (`OPEN`, `PENDING`, `SUBMITTING`, `CONFIRMED`, `FAILED_RETRYABLE`, `FAILED_TERMINAL`). All code referencing old `FAILED` must use `FAILED_RETRYABLE` or `FAILED_TERMINAL`.
- Submit daemon transitions records through `PENDING → SUBMITTING → CONFIRMED` on success, or `PENDING → SUBMITTING → FAILED_RETRYABLE` on transient failure, with `FAILED_RETRYABLE → FAILED_TERMINAL` after exceeding retry threshold.
- Crash recovery on startup resets any `SUBMITTING` records back to `PENDING`.
- `OPEN` state defined in the enum but not used in current flows — reserved for future multi-step commit API.
- Database query functions updated to use new state names (`get_failed_by_chain` queries both `FAILED_RETRYABLE` and `FAILED_TERMINAL`).
- `/verify-chain` uses `CONFIRMED` check (unchanged semantically).

## Capabilities

### New Capabilities
- `trucon-lifecycle-states`: Six-state lifecycle model for commit queue records, with state transition rules, crash recovery for SUBMITTING, and distinction between retryable and terminal failures.

### Modified Capabilities
- `tlog-embedded-submitter`: Submit daemon uses `SUBMITTING` state during active backend calls and distinguishes `FAILED_RETRYABLE` from `FAILED_TERMINAL` on failure.
- `tlog-sequencer`: Crash recovery expanded to reset `SUBMITTING` records to `PENDING` on startup.

## Impact

- **Code**: `src/tc_api/tlog/types.py` (enum), `src/tc_api/trucon/database.py` (7 query functions), `src/tc_api/trucon/app.py` (daemon logic, crash recovery, /commit handler)
- **Tests**: `test_sequencer_refactor.py`, `test_idempotency.py`, `test_tlog_refactored.py` — ~40+ status string literals need updating
- **No DB migration**: status column is TEXT; new values work without schema change
- **No wire format change**: TruCon is internal; tc_api only receives `CommitResponse` (no status field exposed)
