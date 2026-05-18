## Context

The TruCon sequencer currently uses a three-state model (`PENDING`, `CONFIRMED`, `FAILED`) for commit queue records. The architecture (§5.1) specifies six states to provide fine-grained visibility into the submit pipeline. This is a prerequisite for meaningful observability metrics (GAP-04) and accurate status responses (FIX-02).

Current state machine:
```
/commit → PENDING → daemon → CONFIRMED
                  └→ retries exhausted → FAILED
```

The submit daemon treats all failures identically — it increments `retry_count`, and after `MAX_RETRIES` transitions directly to `FAILED`. There is no way to distinguish a transient network timeout from a permanent rejection, and no visibility into whether a record is actively being submitted.

## Goals / Non-Goals

**Goals:**
- Extend `SubmitStatus` enum to 6 states: `OPEN`, `PENDING`, `SUBMITTING`, `CONFIRMED`, `FAILED_RETRYABLE`, `FAILED_TERMINAL`.
- Submit daemon marks records `SUBMITTING` during active backend calls.
- Retry logic distinguishes `FAILED_RETRYABLE` (will auto-retry) from `FAILED_TERMINAL` (requires operator).
- Crash recovery resets `SUBMITTING` records to `PENDING` on startup.
- All database query functions and test assertions updated for new state names.

**Non-Goals:**
- Using `OPEN` state in current flows — reserved for future multi-step commit API.
- Changing TruCon's external API contract (`CommitResponse` has no status field).
- Adding observability metrics — that is GAP-04.
- Database schema migration — the `status` column is TEXT, no DDL needed.

## Decisions

### 1. OPEN state: defined but unused

**Decision**: `OPEN` is added to the `SubmitStatus` enum but not used in any current code path. `/commit` continues to INSERT records as `PENDING`.

**Alternatives considered**:
- (B) tc_api returns `OPEN` from `init_record()` — adds complexity with no consumer.
- (C) TruCon gets a `POST /prepare` endpoint for OPEN→PENDING — new API surface, premature.

**Rationale**: OPEN exists for a future multi-step commit API where records are assembled in TruCon before RTMR extend. Currently assembly happens in tc_api process memory. Defining the enum value now ensures the state machine is complete per architecture.

### 2. Direct replacement of FAILED — no backward compatibility

**Decision**: All occurrences of `FAILED` are replaced with `FAILED_RETRYABLE` or `FAILED_TERMINAL`. No alias, no legacy support.

**Alternatives considered**:
- (A) Map old `FAILED` to `FAILED_TERMINAL` — confusing since semantics differ.
- (B) Keep `FAILED` as alias in enum — dual naming creates ambiguity.

**Rationale**: Development phase with no production data. Clean break is simpler and prevents confusion.

### 3. Crash recovery resets SUBMITTING → PENDING on startup

**Decision**: On TruCon startup, any records in `SUBMITTING` state are reset to `PENDING`. This follows the existing crash recovery pattern (records with `rtmr_extended=FALSE` are deleted on startup).

**Alternatives considered**:
- (B) Timeout-based auto-recovery during daemon tick — adds polling complexity.
- (C) Ignore — single-threaded daemon makes SUBMITTING-stuck unlikely, but not impossible on process crash.

**Rationale**: Startup scan is simple, reliable, and consistent with existing recovery patterns. The daemon is single-threaded so at most one record can be SUBMITTING at crash time.

### 4. State transition rules

```
OPEN        → PENDING         (future: via explicit commit trigger)
PENDING     → SUBMITTING      (daemon picks record for submission)
SUBMITTING  → CONFIRMED       (backend confirms)
SUBMITTING  → FAILED_RETRYABLE (transient failure, retry_count < MAX_RETRIES)
FAILED_RETRYABLE → PENDING    (retry: daemon resets for next attempt)
FAILED_RETRYABLE → FAILED_TERMINAL (retry_count >= MAX_RETRIES)

Invalid transitions (enforced by daemon logic, not DB constraints):
CONFIRMED   → any             (terminal state)
FAILED_TERMINAL → any         (terminal state, requires operator action)
```

The daemon tick loop becomes:
1. For each chain, get `FAILED_TERMINAL` records → block subsequent records.
2. Get `PENDING` records (ordered by sequence_num).
3. For each: `UPDATE status=SUBMITTING` → attempt submit → on success: `CONFIRMED`; on failure: `FAILED_RETRYABLE` with retry check.

## Risks / Trade-offs

- **[More state transitions = more test updates]** → ~40+ test assertions need updating. Mitigated by mechanical find-and-replace pattern.
- **[SUBMITTING window is brief]** → In single-threaded daemon, SUBMITTING duration equals one backend call (~1-30s). Brief but observable. Worth having for metrics hooks (GAP-04).
- **[FAILED_RETRYABLE → PENDING roundtrip]** → Adds one extra UPDATE per retry vs current approach (stay PENDING, increment counter). Trade-off: cleaner state semantics at cost of one extra write per retry cycle.
