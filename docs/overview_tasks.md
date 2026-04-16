# Architecture Gap & Inconsistency Task Overview

> Generated: 2026-04-16
> Source: `docs/architecture.md`, `docs/trusted-log/architecture.md`
> Purpose: Structured task list for closing gaps between architecture docs and implementation.

---

## Task Format

Each task has:
- **ID**: `GAP-<number>` for unimplemented features, `FIX-<number>` for inconsistencies
- **Priority**: HIGH / MEDIUM / LOW
- **Scope**: Which component(s) are affected
- **References**: Architecture doc sections
- **Dependencies**: Other task IDs that must complete first
- **Acceptance Criteria**: Concrete conditions for "done"

---

## Part A: Unimplemented Features

### GAP-01: Docktap → TruCon Event Emission

- **Priority**: HIGH
- **Scope**: `docktap/`, `src/tc_api/trucon/`
- **References**: architecture.md §4.2, §6.2; trusted-log/architecture.md component diagram
- **Dependencies**: None
- **Current State**: Docktap captures Docker runtime events (pull, create, start, stop, rm) and logs them as JSON to stdout via `docktap/proxy/operation_log.py`. There is zero communication with TruCon — no HTTP calls, no event submission, no retry logic.
- **Acceptance Criteria**:
  1. Docktap submits runtime events to TruCon `POST /commit` as signed DSSE bundles.
  2. Retry and acknowledgement handling for transient TruCon failures.
  3. Integration tests for concurrent event submissions from Docktap and REST workers.
- **Related OpenSpec**: `openspec/changes/introduce-trucon-event-orchestrator/` (tasks 3.1, 3.2, 3.3)

---

### ~~GAP-02: Idempotency Key Enforcement~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `src/tc_api/trucon/app.py`, `src/tc_api/trucon/database.py`, `src/tc_api/tlog_client.py`
- **References**: architecture.md §4.3 ("Planned: Idempotency key enforcement"), §7
- **Dependencies**: None
- **Completed**: 2026-04-16 | Archive: `openspec/changes/archive/2026-04-16-idempotency-key-enforcement/`
- **Acceptance Criteria**:
  1. ✅ `CommitRequest` accepts an optional `idempotency_key` field.
  2. ✅ `commit_queue` table has a UNIQUE `idempotency_key` column (via unique index for migration compat).
  3. ✅ Duplicate commits with the same key return the original `CommitResponse` without re-extending RTMR.
  4. ⏳ `idempotency_hit_count` metric — deferred to GAP-04 (observability metrics). The dedup code path exists; metric instrumentation is not yet wired.
- **Tests**: `tests/test_idempotency.py` (13 tests, all passing)

---

### GAP-03: Workload / Instance Mapping Model

- **Priority**: HIGH
- **Scope**: `src/tc_api/trucon/`
- **References**: architecture.md §5.2
- **Dependencies**: GAP-01 (Docktap integration provides instance lifecycle events)
- **Current State**: No `workload_id`, `instance_id` tables or query paths. No correlation views.
- **Acceptance Criteria**:
  1. SQLite tables for `workload_id → instance_id[]` and `instance_id → event_id[]` mappings.
  2. TruCon endpoints to query mappings (e.g., `GET /workloads/{id}/instances`, `GET /instances/{id}/events`).
  3. Audit tooling can resolve workload → instance → event chain relationships.

---

### GAP-04: Observability Metrics

- **Priority**: HIGH
- **Scope**: `src/tc_api/trucon/app.py`, `src/tc_api/main.py`
- **References**: architecture.md §8.2
- **Dependencies**: ~~GAP-02~~ ✅, ~~GAP-06~~ ✅ (granular states now available for `terminal_failure_count` metric)
- **Current State**: Zero metrics instrumentation. The architecture requires 7 minimum metrics.
- **Acceptance Criteria**:
  All of the following metrics are emittable (e.g., via Prometheus client or structured log):
  1. `queue_depth` — number of PENDING records
  2. `commit_latency` — time from `/commit` request to response
  3. `submit_latency` — time from daemon pickup to backend confirmation
  4. `confirmation_lag` — time from commit to confirmed
  5. `retry_count` — cumulative retries across records
  6. `terminal_failure_count` — records in FAILED state
  7. `idempotency_hit_count` — duplicate commit detections

---

### GAP-05: Event Log 0 (Baseline Record)

- **Priority**: MEDIUM
- **Scope**: `src/tc_api/tlog_client.py`, `src/tc_api/trucon/app.py`
- **References**: trusted-log/architecture.md §Event Log 0, §Trust Log Initialization Flow
- **Dependencies**: None
- **Current State**: No initialization-time baseline record. No RTMR snapshot capture. No CCEL system event log query. The `pub_key` field on `EventLog` type exists but is always `None`.
- **Acceptance Criteria**:
  1. On Trust Bootstrap initialization, Trusted Log creates Event Log 0 from the current RTMR snapshot and baseline system-event metadata.
  2. Event Log 0 does NOT perform an RTMR extend — it captures the current MR value as baseline.
  3. Event Log 0 is committed locally and published to the immutable backend.
  4. The caller's public key is embedded in Event Log 0's `pub_key` field.
  5. Initialization is not complete until Event Log 0 is confirmed remotely.

---

### ~~GAP-06: Granular Lifecycle States~~ ✅ COMPLETED

- **Priority**: MEDIUM
- **Scope**: `src/tc_api/trucon/app.py`, `src/tc_api/trucon/database.py`, `src/tc_api/tlog/types.py`
- **References**: architecture.md §5.1
- **Dependencies**: None
- **Completed**: 2026-04-16 | Archive: `openspec/changes/archive/2026-04-16-granular-lifecycle-states/`
- **Acceptance Criteria**:
  1. ✅ `SubmitStatus` enum extended with: `OPEN`, `SUBMITTING`, `FAILED_RETRYABLE`, `FAILED_TERMINAL` (6 states total).
  2. ✅ Submit daemon uses `SUBMITTING` during active backend call.
  3. ✅ Retry logic distinguishes `FAILED_RETRYABLE` (retry scheduled) from `FAILED_TERMINAL` (operator intervention needed).
  4. ⏳ `OPEN` state reserved in enum but not yet used — deferred until pre-commit assembly flow is implemented.
- **Tests**: `tests/test_lifecycle_states.py` (11 tests), existing tests updated (60 total, all passing)

---

### GAP-07: On-Chain Backend Adapter

- **Priority**: MEDIUM
- **Scope**: `src/tc_api/trucon/adapters/`
- **References**: trusted-log/architecture.md component diagram (OnChain implementation)
- **Dependencies**: None
- **Current State**: Only `SigstoreLogAdapter` (Rekor/transparent-log) exists. The `ImmutableLogAdapter` abstract interface is defined in `src/tc_api/tlog/immutable.py`, but no on-chain implementation exists.
- **Acceptance Criteria**:
  1. `OnChainAdapter` class implementing `ImmutableLogAdapter`.
  2. `submit_bundle()`, `get_entry()`, `traverse()` implemented for on-chain target.
  3. Submit daemon can be configured to use on-chain backend (alongside or instead of Rekor).

---

### GAP-08: Feature-Flag Fallback to Legacy Write Path

- **Priority**: MEDIUM
- **Scope**: `src/tc_api/main.py`, `src/tc_api/config.py`
- **References**: architecture.md §8.1, §11
- **Dependencies**: None
- **Current State**: No routing/feature controls. No legacy fallback. If TruCon is unavailable, commit simply fails.
- **Acceptance Criteria**:
  1. A feature flag (e.g., `ENABLE_LEGACY_FALLBACK`) in config.
  2. When TruCon is unreachable and flag is enabled, REST API falls back to a legacy direct-write path.
  3. Fallback is logged and observable.

---

### GAP-09: `prev_log_id` as Secondary Ordering (Non-TEE Mode)

- **Priority**: MEDIUM
- **Scope**: `src/tc_api/tlog_client.py`, `src/tc_api/trucon/app.py`
- **References**: trusted-log/architecture.md §"Future: prev_log_id as a Secondary Ordering Method"
- **Dependencies**: None
- **Current State**: `prev_log_id` is excluded from the DSSE predicate. In non-TEE environments (no RTMR), there is no alternative ordering proof.
- **Acceptance Criteria**:
  1. When TDX hardware is unavailable, `prev_log_id` is included in the DSSE-signed predicate.
  2. Verification logic validates `prev_log_id` chain for software-only deployments.
  3. Mode selection (hardware vs software ordering) is explicit and configurable.

---

### GAP-10: Internal Service Authentication

- **Priority**: MEDIUM
- **Scope**: `src/tc_api/trucon/app.py`, `src/tc_api/tlog_client.py`
- **References**: architecture.md §9
- **Dependencies**: None
- **Current State**: tc_api → TruCon calls are unauthenticated HTTP on localhost. Architecture requires "Internal service calls must be authenticated and authorized."
- **Acceptance Criteria**:
  1. TruCon endpoints require a valid service token or mutual TLS for internal calls.
  2. tc_api attaches credentials when calling TruCon.
  3. Unauthorized requests are rejected with appropriate HTTP status.

---

## Part B: Implementation Inconsistencies (Code Diverges from Architecture)

### ~~FIX-01: Digest Algorithm — Two-Level Hashing Not Implemented~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `src/tc_api/tlog_client.py`
- **References**: trusted-log/architecture.md §Digest Algorithm
- **Completed**: 2026-04-16 | Archive: `openspec/changes/archive/2026-04-16-two-level-digest-hashing/`
- **Acceptance Criteria**:
  1. ✅ Each entry is individually hashed: `SHA384(canonical_json({"key": k, "value": v}))`.
  2. ✅ Event digest is computed over `{event_id, event_type, created, [entry_digest_1, ...]}`.
  3. ✅ Both entries and entry digests included in DSSE predicate for auditability.
  4. No backward compatibility needed (no existing records in old format).
- **Tests**: `tests/test_two_level_digest.py` (13 tests, all passing)

---

### FIX-02: `GET /status` Response Shape Mismatches `LatestState` / `CommitQueueStatus`

- **Priority**: MEDIUM
- **Scope**: `src/tc_api/trucon/app.py`, `src/tc_api/tlog/types.py`
- **References**: trusted-log/architecture.md §Data Structures
- **Current Behavior**: `GET /status` returns `QueueStatusResponse(queued_count, failed_count, next_sequence_num)`.
- **Architecture Requires**:
  - `CommitQueueStatus`: `has_queued_records: bool`, `queued_record_count: int`, `next_record_id: Optional[str]`
  - `LatestState`: `latest_confirmed_log_id`, `pending_record_count`, `pending_event_ids[]`, `latest_mr_value`
- **Acceptance Criteria**:
  1. `GET /status` response matches the `CommitQueueStatus` contract (use `next_record_id`, not `next_sequence_num`).
  2. A separate endpoint or extended response provides `LatestState` fields: `latest_confirmed_log_id`, `pending_event_ids[]`, `latest_mr_value`.
  3. Type definitions in `tlog/types.py` match the actual API response.

---

### FIX-03: `SubmitResult` Type Defined but Never Exposed

- **Priority**: LOW
- **Scope**: `src/tc_api/tlog/types.py`, `src/tc_api/trucon/app.py`
- **References**: trusted-log/architecture.md §Data Structures, §Message Flow step 4
- **Current Behavior**: `SubmitResult` dataclass exists in `types.py` but is never returned by any endpoint or API call. The submit daemon updates records internally without producing a `SubmitResult`.
- **Acceptance Criteria**:
  1. Decide: either expose `SubmitResult` via a query endpoint (e.g., `GET /records/{record_id}`) or remove the unused type.
  2. If exposed, daemon transitions should produce `SubmitResult` objects that are queryable.

---

### FIX-04: Entry Type Too Narrow for Architecture's Rich Entry Schema

- **Priority**: LOW
- **Scope**: `src/tc_api/tlog/types.py`, `src/tc_api/tlog_client.py`
- **References**: trusted-log/architecture.md §JSON Mock-Up
- **Current Behavior**: `Entry` is `@dataclass(key: str, value: str)`. All structured data (image_hash, sbom_format, cmd, etc.) is flattened into these two strings.
- **Architecture Shows**: Rich entry objects with `name`, `image_hash`, `image_size`, `cmd`, `created`, `digest` fields.
- **Acceptance Criteria**:
  1. Decide: either extend `Entry` to support structured metadata, or document that `key`/`value` is the canonical wire format and rich fields are caller conventions.
  2. If extended, update `add_entry()` API and digest computation.

---

## Part C: Open Architecture Questions (Unresolved in Code)

These are not implementation tasks but **design decisions** that should be resolved before certain GAP tasks can proceed.

| ID | Question | Blocks | Architecture Ref |
|----|----------|--------|------------------|
| Q-01 | Chain scope default: per workload, per tenant, or global? | GAP-03 | architecture.md §12 |
| Q-02 | Confirmation SLA target from commit to backend confirmed? | GAP-04 | architecture.md §12 |
| Q-03 | Canonical mandatory fields for stable instance mapping across restarts? | GAP-03 | architecture.md §12 |
| Q-04 | Worker ownership model: local ownership or shared lease? | — | architecture.md §12 |
| Q-05 | How to handle runtimes that allow quote/report reads but not MR extend? | GAP-05 | trusted-log/architecture.md §Trust Log Initialization |

---

## Dependency Graph

```
Q-01 ──────┐
Q-03 ──────┼──▶ GAP-03 (Mapping Model)
GAP-01 ────┘         │
                      ▼
               GAP-04 (Observability) ◀── GAP-02 ✅, GAP-06 ✅
                      │
                      ▼
               [operational baseline]

GAP-05 (Event Log 0) ◀── Q-05
GAP-07 (On-Chain Adapter) ── standalone
GAP-08 (Feature-Flag Fallback) ── standalone
GAP-09 (Non-TEE Ordering) ── standalone
GAP-10 (Service Auth) ── standalone

FIX-02 (Status Response) ── standalone
FIX-03 (SubmitResult) ── standalone
FIX-04 (Entry Type) ── standalone

✅ DONE: GAP-02, FIX-01, GAP-06
```

---

## Suggested Execution Order

**Phase 1 — Fix inconsistencies & foundational gaps** (no design questions needed):
1. ~~`FIX-01`~~ ✅ completed 2026-04-16
2. ~~`GAP-02`~~ ✅ completed 2026-04-16
3. ~~`GAP-06`~~ ✅ completed 2026-04-16
4. `FIX-02` — Status response shape (MEDIUM, standalone) ← **next**

**Phase 2 — Core infrastructure** (all Phase 1 dependencies met):
5. `GAP-04` — Observability metrics (dependencies GAP-02 ✅, GAP-06 ✅ — ready)
6. `GAP-05` — Event Log 0 (after Q-05 resolved)
7. `GAP-09` — Non-TEE ordering mode

**Phase 3 — Integration** (requires design decisions Q-01, Q-03):
8. `GAP-01` — Docktap → TruCon event emission
9. `GAP-03` — Workload/instance mapping (after GAP-01)
10. `GAP-10` — Internal service authentication

**Phase 4 — Extensions**:
11. `GAP-07` — On-chain backend adapter
12. `GAP-08` — Feature-flag fallback
13. `FIX-03` — SubmitResult exposure
14. `FIX-04` — Entry type enrichment
