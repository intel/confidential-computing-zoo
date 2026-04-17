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

### ~~GAP-01: Docktap → TruCon Event Emission~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `docktap/`, `src/tc_api/trucon/`
- **References**: architecture.md §4.2, §6.2; trusted-log/architecture.md component diagram
- **Dependencies**: None
- **Completed**: 2026-04-17 | Archive: `openspec/changes/archive/2026-04-17-docktap-trucon-emission/`
- **Design Decisions** (confirmed 2026-04-17):
  - **Signing identity**: Docktap shares tc_api's signing infrastructure — uses the same `sigstore.oidc.detect_credential()` ambient OIDC mechanism. Token re-acquired on each commit (no caching).
  - **Event granularity**: Each Docker operation = one independent TruCon commit. Uses existing flat `Entry(key, value)` format (rich Entry type deferred to FIX-04).
  - **Chain assignment**: v1 uses `"default"` chain_id. Per-workload chain_id assignment deferred to GAP-11.
  - **Failure handling**: Synchronous + best-effort — TruCon failure logs a warning but does NOT block the Docker response back to CLI.
  - **Cross-source ordering**: REST and Docktap events on the same chain get serialized `sequence_num` ordering via TruCon's lock. No additional causal ordering enforcement.
  - **Submitted operation types**: `pull`, `create`, `start`, `stop`, `rm` only. Other operations (`wait`, `rmi`, `image_inspect`, `inspect`, `preflight_ping`, `preflight_info`, `unknown`) are not submitted.
  - **OIDC token**: Re-acquire each time via same ambient credential source as tc_api. No token caching in Docktap.
- **Acceptance Criteria**:
  1. ✅ Docktap submits `pull`/`create`/`start`/`stop`/`rm` events to TruCon `POST /commit` as signed DSSE bundles using shared OIDC signing.
  2. ✅ Best-effort submission: TruCon failures log a warning and do not block the Docker API response.
  3. ✅ Integration tests for concurrent event submissions from Docktap and REST workers verifying `sequence_num` ordering.
- **Tests**: `docktap/tests/test_trucon_client.py` (25 tests), `docktap/tests/test_docktap_integration.py` (3 tests); 129 total regression pass
- **Related OpenSpec**: `openspec/changes/archive/2026-04-17-docktap-trucon-emission/`

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
  4. ✅ `idempotency_hit_count` metric — implemented in GAP-04 (`metric=idempotency_hit` log emission).
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

### ~~GAP-04: Observability Metrics~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `src/tc_api/trucon/app.py`, `src/tc_api/trucon/database.py`, `src/tc_api/tlog/types.py`, `src/tc_api/tlog_client.py`
- **References**: architecture.md §8.2
- **Dependencies**: ~~GAP-02~~ ✅, ~~GAP-06~~ ✅
- **Completed**: 2026-04-17 | Archive: `openspec/changes/archive/2026-04-17-observability-metrics/`
- **Acceptance Criteria**:
  All 7 architecture-required metrics are emitted via structured logging:
  1. ✅ `queue_depth` — emitted in `metric=queue_snapshot` each daemon tick
  2. ✅ `commit_latency` — `metric=commit_latency` with `latency_ms`, `record_id`, `idempotent`
  3. ✅ `submit_latency` — `metric=submit_latency` with `latency_ms`, `record_id`, `outcome`
  4. ✅ `confirmation_lag` — `metric=confirmation_lag` with `lag_ms` (requires `created_at` column)
  5. ✅ `retry_count` — `total_retry_count` in `get_queue_stats()` and `GET /status` response
  6. ✅ `terminal_failure_count` — in `metric=queue_snapshot`
  7. ✅ `idempotency_hit_count` — `metric=idempotency_hit` with `key`, `chain_id`, `record_id`
  Additionally:
  - ✅ `created_at TEXT` column added to `commit_queue` (DDL migration + backfill)
  - ✅ `total_retry_count: int` added to `CommitQueueStatusResponse` and `CommitQueueStatus`
- **Tests**: `tests/test_observability_metrics.py` (8 tests); 81 total regression pass

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

### ~~GAP-09: `prev_log_id` as DB-Level Ordering Verification (Non-TEE Mode)~~ ✅ COMPLETED

- **Priority**: MEDIUM
- **Scope**: `src/tc_api/trucon/app.py`
- **References**: trusted-log/architecture.md §"Non-TEE Mode: prev_log_id as DB-Level Ordering Verification"
- **Dependencies**: None
- **Completed**: 2026-04-17 | Archive: `openspec/changes/archive/2026-04-17-non-tee-verification/`
- **Design Decisions** (confirmed 2026-04-17):
  - `prev_log_id` stays OUT of the DSSE predicate (no signing change). This is DB-level verification, not cryptographic proof.
  - Unconfirmed chain tail: accepted as unverifiable (prev_log_id depends on log_id assignment at confirmation time).
  - Response model: keep existing `rtmr_available: bool` field, no new verification-mode field.
  - Startup warning: upgrade to `logger.warning()` with clear non-TEE banner.
  - Auto-detect only (via TDX sysfs presence). No explicit env var override.
- **Acceptance Criteria**:
  1. ✅ `verify-chain` checks `prev_log_id` linkage for confirmed records when `rtmr_available == False`.
  2. ✅ TruCon logs a prominent warning at startup when running without TDX hardware.
  3. ✅ No changes to signing flow, DSSE predicate format, or commit flow.
- **Tests**: `tests/test_non_tee_verification.py` (5 tests, all passing)

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

### GAP-11: Per-Workload Chain Assignment for Docktap

- **Priority**: MEDIUM
- **Scope**: `docktap/`, `src/tc_api/trucon/`
- **References**: architecture.md §4.2, §7; Q-01
- **Dependencies**: GAP-01 (basic Docktap → TruCon emission must work first)
- **Current State**: GAP-01 v1 uses `"default"` chain_id for all Docktap events. This task upgrades to per-workload chain assignment.
- **Design Notes**: Preferred mechanism is a container label convention (e.g., `--label tc.workload_id=xxx`) extracted from `docker create` request body. Subsequent operations (`start`/`stop`/`rm`) resolve workload_id by looking up the container_id in Docktap's `OperationTracker`. Containers without the label fall back to `"default"` chain.
- **Acceptance Criteria**:
  1. Docktap extracts `tc.workload_id` from container labels during `create` operations.
  2. Subsequent lifecycle events for the same container use the resolved `workload_id` as `chain_id`.
  3. Containers without `tc.workload_id` label default to `"default"` chain.
  4. Tests cover label extraction, cross-operation chain resolution, and fallback behavior.

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

### ~~FIX-02: `GET /status` Response Shape Mismatches `LatestState` / `CommitQueueStatus`~~ ✅ COMPLETED

- **Priority**: MEDIUM
- **Scope**: `src/tc_api/trucon/app.py`, `src/tc_api/trucon/database.py`, `src/tc_api/tlog_client.py`
- **References**: trusted-log/architecture.md §Data Structures
- **Completed**: 2026-04-17 | Archive: `openspec/changes/archive/2026-04-17-status-response-fix/`
- **Acceptance Criteria**:
  1. ✅ `GET /status` returns `CommitQueueStatusResponse` matching `CommitQueueStatus` contract (`has_queued_records`, `queued_record_count`, `next_record_id`) plus granular GAP-06 counts.
  2. ✅ New `GET /state` endpoint returns `LatestStateResponse` with `latest_confirmed_log_id`, `pending_event_ids[]`, `latest_mr_value` for default chain.
  3. ✅ `tlog_client.py` properly maps new field names and populates `next_record_id`.
  4. ✅ Old `QueueStatusResponse` model removed.
- **Tests**: `tests/test_status_response.py` (15 tests, all passing); 73 total regression pass

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

| ID | Question | Blocks | Architecture Ref | Status |
|----|----------|--------|------------------|--------|
| Q-01 | Chain scope default: per workload, per tenant, or global? | GAP-03, GAP-11 | architecture.md §12 | **Partially resolved** (2026-04-17): Target is per-workload. GAP-01 v1 uses `"default"` chain. Per-workload assignment deferred to GAP-11. |
| Q-02 | Confirmation SLA target from commit to backend confirmed? | GAP-04 | architecture.md §12 | Open |
| Q-03 | Canonical mandatory fields for stable instance mapping across restarts? | GAP-03 | architecture.md §12 | Open |
| Q-04 | Worker ownership model: local ownership or shared lease? | — | architecture.md §12 | Open |
| Q-05 | How to handle runtimes that allow quote/report reads but not MR extend? | GAP-05 | trusted-log/architecture.md §Trust Log Initialization | Open |

---

## Dependency Graph

```
GAP-01 (Docktap → TruCon, v1 default chain) ✅
  │
  ├──▶ GAP-11 (Per-Workload Chain Assignment) ← **next**
  │         │
  │         ▼
  │    Q-01 ──────┐
  │    Q-03 ──────┼──▶ GAP-03 (Mapping Model)
  │               │
  └───────────────┘

GAP-05 (Event Log 0) ◀── Q-05
GAP-07 (On-Chain Adapter) ── standalone
GAP-08 (Feature-Flag Fallback) ── standalone
GAP-09 (Non-TEE Ordering) ✅ ── standalone
GAP-10 (Service Auth) ── standalone
GAP-11 (Per-Workload Chain) ◀── GAP-01 ✅

FIX-03 (SubmitResult) ── standalone
FIX-04 (Entry Type) ── standalone (Docktap will benefit when done)

✅ DONE: GAP-02, FIX-01, GAP-06, FIX-02, GAP-04, GAP-09, GAP-01
```

---

## Suggested Execution Order

**Phase 1 — Fix inconsistencies & foundational gaps** ✅ COMPLETE:
1. ~~`FIX-01`~~ ✅ completed 2026-04-16
2. ~~`GAP-02`~~ ✅ completed 2026-04-16
3. ~~`GAP-06`~~ ✅ completed 2026-04-16
4. ~~`FIX-02`~~ ✅ completed 2026-04-17

**Phase 2 — Core infrastructure** (in progress):
5. ~~`GAP-04`~~ ✅ completed 2026-04-17
6. `GAP-05` — Event Log 0 (after Q-05 resolved)
7. ~~`GAP-09`~~ ✅ completed 2026-04-17

**Phase 3 — Docktap Integration** (in progress):
8. ~~`GAP-01`~~ ✅ completed 2026-04-17
9. `GAP-11` — Per-workload chain assignment for Docktap (after GAP-01) ← **next**
10. `GAP-03` — Workload/instance mapping (after GAP-11, requires Q-01 fully resolved, Q-03)
11. `GAP-10` — Internal service authentication

**Phase 4 — Extensions**:
12. `GAP-07` — On-chain backend adapter
13. `GAP-08` — Feature-flag fallback
14. `FIX-03` — SubmitResult exposure
15. `FIX-04` — Entry type enrichment (Docktap and REST both benefit)
