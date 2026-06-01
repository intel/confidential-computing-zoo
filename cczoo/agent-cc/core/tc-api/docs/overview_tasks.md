# Architecture Gap & Inconsistency Task Overview

> Generated: 2026-04-16
> Last Updated: 2026-06-01
> Source: `docs/architecture.md`, `../../tlog/docs/trusted-log/architecture.md`
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

## Part 0: Current Large Change Breakdown

### GAP-13: Public Predecessor Replay Links via Two-Phase Intent Reservation

- **Priority**: HIGH
- **Scope**: `tc_api/transparency/commit_client.py`, `tc_api/trucon/app.py`, `tc_api/trucon/database.py`, `tlog/tlog/backends/rekor/adapter.py`, `tc_api/identity/sigstore_baseline.py`, `tests/`, `docs/`
- **References**: archived OpenSpec changes `2026-04-22-reservation-backed-replay-intents` and `2026-04-22-public-predecessor-replay-diagnostics`; architecture.md replay / verification sections; trusted-log verification docs
- **Dependencies**: GAP-05 ✅, GAP-09 ✅, GAP-10 ✅, GAP-12 ✅
- **Status**: PARTIALLY COMPLETED
- **Completed Milestones**: 2026-04-22 reservation-backed commit intents and predecessor replay diagnostics archived after implementation and validation.
- **Current implementation state**:
  - TruCon now performs a durable reservation step under the sequencer lock and returns a single-use intent token plus the final predecessor contract (`sequence_num`, `prev_event_digest`, `prev_lookup_hash`).
  - tc_api now signs DSSE using those reserved values and submits the signed bundle together with the `intent_token`.
  - TruCon validates the submitted bundle against the reserved contract before enqueueing it.
  - Immutable replay, TruCon verification, and CLI verification now treat signed predecessor fields as protocol truth and use Rekor payload-hash lookup as candidate discovery only.
  - Immutable replay can now re-materialize hash-only public Rekor DSSE entries from a non-authoritative OCI bundle mirror keyed by `payload_hash`, including registry-backed mirrors.
  - Replay candidate selection now prefers materialized `attestation-storage` or mirror-backed forms over public hash-only duplicates when they share the same Rekor identity and `payload_hash`, and traversal uses the same rule for predecessor-hop resolution.
  - Opt-in real integration coverage now includes a public Rekor + real OCI mirror + real verify multi-chain smoke path driven from `tc_api.identity.oidc_preflight --fetch`.
  - Remaining work is mostly rollout hardening and legacy compatibility cleanup rather than primary protocol design.

#### Task 13.1: Define the reservation protocol and state model

- **Priority**: HIGH
- **Scope**: `tc_api/trucon/app.py`, `tc_api/trucon/database.py`, protocol docs
- **Dependencies**: None
- **Goal**: Introduce an explicit `reserve -> sign -> commit` control flow with a stable predecessor contract.
- **Questions already resolved for implementation direction**:
  - Reservation should return the final public predecessor contract.
  - Intent tokens should be single-use and time-bounded.
  - Idempotency should bind to the reservation / intent lifecycle.
- **Acceptance Criteria**:
  1. ✅ TruCon exposes a reservation API that returns `sequence_num`, `prev_event_digest`, `prev_lookup_hash`, and an intent token.
  2. ✅ The reservation result is stable across idempotent retries of the same business request.
  3. ✅ Reservation state has explicit lifecycle semantics: active, consumed, expired, or cancelled/garbage-collected.
  4. ✅ Crash recovery and restart behavior for unconsumed reservations is documented.

#### Task 13.2: Extend Event Log 0 and lazy baseline to the same signed replay contract

- **Priority**: HIGH
- **Scope**: `tc_api/sigstore_baseline.py`, `tc_api/trucon/app.py`, init/lazy baseline tests
- **Dependencies**: Task 13.1
- **Goal**: Make baseline records the null-predecessor instance of the same replay protocol, including lazy workload baseline creation.
- **Acceptance Criteria**:
  1. ✅ Event Log 0 signed payload includes `sequence_num = 1`, `prev_event_digest = null`, and `prev_lookup_hash = null`.
  2. ✅ Lazy workload baseline creation participates in the same predecessor protocol rather than acting as an unrelated side effect.
  3. ✅ The first non-baseline event after initialization references the baseline through `prev_event_digest` and `prev_lookup_hash`.
  4. ✅ Historical first-event workload-chain concurrency behavior was deterministic before the default-only rollback. Current measured-chain behavior uses only `default`.

#### Task 13.3: Move tc_api commit flow onto reservation-backed signing

- **Priority**: HIGH
- **Scope**: `tc_api/transparency/commit_client.py`, internal transport helpers
- **Dependencies**: Task 13.1, Task 13.2
- **Goal**: Replace the current one-shot `sign -> /commit` path with reservation-backed DSSE signing.
- **Acceptance Criteria**:
  1. ✅ tc_api requests a reservation before constructing the signed DSSE predicate.
  2. ✅ The DSSE predicate includes signed `chain_id`, `sequence_num`, `digest`, `prev_event_digest`, and `prev_lookup_hash`.
  3. ✅ tc_api submits the signed bundle together with the intent token.
  4. ✅ The commit path remains safe under concurrent submissions to the same chain.

#### Task 13.4: Validate reserved contract at TruCon commit time and persist replay metadata

- **Priority**: HIGH
- **Scope**: `tc_api/trucon/app.py`, `tc_api/trucon/database.py`
- **Dependencies**: Task 13.3
- **Goal**: Ensure TruCon treats the intent token as a strong consistency constraint rather than a weak hint.
- **Acceptance Criteria**:
  1. ✅ TruCon parses the submitted bundle and verifies its signed predecessor fields match the reservation.
  2. ✅ Mismatched or expired intent tokens are rejected without mutating chain state.
  3. ✅ Persisted record state includes enough replay metadata to support verification and operational debugging.
  4. ✅ Existing submit-daemon responsibilities remain limited to immutable-log submission rather than predecessor assignment.

#### Task 13.5: Rework immutable replay and TruCon verification around signed predecessor proof

- **Priority**: HIGH
- **Scope**: `tc_api/transparency/commit_client.py`, `tlog/tlog/backends/rekor/adapter.py`, `tc_api/trucon/app.py`, CLI verify paths
- **Dependencies**: Task 13.4
- **Goal**: Replace `prev_log_id`-based public continuity checks with signed predecessor verification.
- **Acceptance Criteria**:
  1. ✅ Immutable replay queries Rekor by `prev_lookup_hash` and treats the result as candidate discovery only.
  2. ✅ Candidate filtering enforces `chain_id`, `sequence_num - 1`, and recomputed `prev_event_digest`.
  3. ✅ `/verify-chain` reports `prev_event_digest`-based continuity results and predecessor candidate counts for the default measured chain.
  4. ✅ Pending / unconfirmed records remain representable without falsely reporting predecessor success.
- **Implementation Note**: verifier-facing continuity now uses `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` as protocol truth. `prev_log_id` remains only in local bookkeeping, compatibility parsing, and some legacy traversal fallbacks.
- **Implementation Note**: `prev_lookup_hash` discovery is not first-result-wins. When Rekor lookup yields both a public hash-only candidate and a replayable `attestation-storage` or mirror-backed candidate for the same logical predecessor, replay and traversal now keep the materialized candidate.

#### Task 13.6: Finish regression coverage, rollout rules, and operator documentation

- **Priority**: MEDIUM
- **Scope**: `tests/`, `docs/architecture.md`, `../../tlog/docs/trusted-log/`, public Rekor smoke tests
- **Dependencies**: Task 13.5
- **Goal**: Make the protocol change safe to ship and understandable to operators.
- **Status**: PARTIALLY COMPLETED
- **Acceptance Criteria**:
  1. ✅ Unit tests cover reservation lifecycle, idempotent retry semantics, baseline null-predecessor behavior, and missing/multiple Rekor candidates.
  2. ◐ Public Rekor opt-in integration tests now validate real signing, baseline paths, immutable replay, and a real OCI mirror-backed multi-chain verification smoke; mixed-regime and broader rollout coverage remain limited.
  3. ✅ Documentation clearly explains that Rekor `/api/v1/index/retrieve` is best-effort candidate discovery, not protocol truth.
  4. ◐ Rollout guidance for mixed-format chains is clearer for operators now, but legacy cleanup rules still need tightening.

---

## Part A: Unimplemented Features

### ~~GAP-01: Docktap → TruCon Event Emission~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `tc_api/docktap/`, `tc_api/trucon/`
- **References**: architecture.md §4.2, §6.2; ../../tlog/docs/trusted-log/architecture.md component diagram
- **Dependencies**: None
- **Completed**: 2026-04-17 | Archive: `openspec/changes/archive/2026-04-17-docktap-trucon-emission/`
- **Design Decisions** (confirmed 2026-04-17):
  - **Signing identity**: The original implementation shared tc_api's ambient OIDC / Sigstore path. Current runtime authorization has since evolved: Docktap now defaults to explicit delegation for runtime operations, while `delegation_disabled` preserves the stricter token-per-operation posture.
  - **Event granularity**: Each Docker operation = one independent TruCon commit. Uses `Entry(key, value)` objects with native JSON values (FIX-04 completed: `value: Any`).
  - **Chain assignment**: current measured-chain behavior uses `"default"` only. Earlier notes about per-workload chain_id assignment are superseded by the later default-only rollback.
  - **Failure handling**: Synchronous + best-effort — TruCon failure logs a warning but does NOT block the Docker response back to CLI.
  - **Cross-source ordering**: REST and Docktap events on the same chain get serialized `sequence_num` ordering via TruCon's lock. No additional causal ordering enforcement.
  - **Submitted operation types**: `pull`, `create`, `start`, `stop`, `rm` only. Other operations (`wait`, `rmi`, `image_inspect`, `inspect`, `preflight_ping`, `preflight_info`, `unknown`) are not submitted.
  - **Current auth model note**: Runtime operations now default to `DOCKTAP_AUTH_MODE=explicit_delegation`; operators normally create one `session.delegation` event on `docktap-runtime` and later owner-key-signed runtime events reference that grant through `delegation_id`.
- **Acceptance Criteria**:
  1. ✅ Docktap submits `pull`/`create`/`start`/`stop`/`rm` events to TruCon `POST /commit` as signed DSSE bundles. Current builds support both the explicit-delegation owner-key path and the stricter OIDC-only override path.
  2. ✅ Best-effort submission: TruCon failures log a warning and do not block the Docker API response.
  3. ✅ Integration tests for concurrent event submissions from Docktap and REST workers verifying `sequence_num` ordering.
- **Tests**: `docktap/tests/test_trucon_client.py` (25 tests), `docktap/tests/test_docktap_integration.py` (3 tests); 129 total regression pass
- **Related OpenSpec**: `openspec/changes/archive/2026-04-17-docktap-trucon-emission/`

---

### ~~GAP-02: Idempotency Key Enforcement~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `tc_api/trucon/app.py`, `tc_api/trucon/database.py`, `tc_api/transparency/commit_client.py`
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

### ~~GAP-03: Workload / Instance Mapping Model~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `tc_api/trucon/`, `tc_api/docktap/trucon_client.py`, `tc_api/transparency/commit_client.py`
- **References**: architecture.md §5.2
- **Dependencies**: GAP-01 ✅, GAP-11 ✅
- **Completed**: 2026-04-17 | Archive: `openspec/changes/archive/2026-04-17-workload-instance-mapping/`
- **Design Decisions** (confirmed 2026-04-17):
  - **Instance identity (Q-03 resolved)**: `instance_id` = full 64-character Docker `container_id`. One `create→rm` lifecycle = one instance.
  - **Data model**: No separate mapping tables. `instance_id TEXT` column added to `commit_queue`; workload→instance→event queries derived via SQL aggregation.
  - **Metadata flow**: `instance_id` is caller-provided metadata on `CommitRequest` (same pattern as `chain_id`), outside the DSSE signed predicate.
  - **Query endpoints**: `GET /workloads/{id}/instances`, `GET /instances/{id}/events`, `GET /workloads/{id}/events` on TruCon.
  - **Docktap**: Passes `container_id` as `instance_id` for container lifecycle events; `null` for `pull` operations.
- **Acceptance Criteria**:
  1. `commit_queue` includes `instance_id TEXT` column with composite index on `(chain_id, instance_id)`.
  2. TruCon query endpoints for workload→instance and instance→event lookups.
  3. Docktap and tc_api attach `instance_id` to commit requests when applicable.
  4. Audit tooling can resolve workload → instance → event chain relationships.
- **OpenSpec**: `openspec/changes/archive/2026-04-17-workload-instance-mapping/`

---

### ~~GAP-04: Observability Metrics~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `tc_api/trucon/app.py`, `tc_api/trucon/database.py`, `tlog/tlog/types.py`, `tc_api/transparency/commit_client.py`
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

### ~~GAP-05: Event Log 0 (Baseline Record)~~ ✅ COMPLETED

- **Priority**: MEDIUM
- **Scope**: `tc_api/transparency/commit_client.py`, `tc_api/trucon/app.py`, `tc_api/trucon/adapters/tdx_mr.py`, `tc_api/trucon/adapters/ccel.py`
- **References**: ../../tlog/docs/trusted-log/architecture.md §Event Log 0, §Trust Log Initialization Flow
- **Dependencies**: None (Q-05 resolved)
- **Completed**: 2026-04-17 | Archive: `openspec/changes/archive/2026-04-17-event-log-0-baseline/`
- **Design Decisions** (confirmed 2026-04-17):
  - **Platform scope**: TDX only. AMD SEV-SNP / quote-only runtimes are out of scope. Q-05 is resolved: not applicable.
  - **RTMR register**: Only RTMR[2] is used (OS/application layer). RTMR[0]/[1] are firmware/boot-locked. Hardcoded `index=0` corrected to `index=2` via `RTMR_INDEX = 2` constant.
  - **New endpoint**: Two-phase `/init-chain` protocol on TruCon:
    - Phase 1: `GET /init-chain/{chain_id}/baseline` → reads RTMR[2] (no extend), computes CCEL SHA-384 digest, returns `{rtmr_value, ccel_digest, init_token}`.
    - Phase 2: `POST /init-chain` with `{chain_id, init_token, signed_bundle, pub_key}` → validates token, verifies no existing chain, INSERTs baseline record, initializes `chain_state`.
  - **Signing**: tc_api generates ECDSA P-384 keypair in TEE memory, signs DSSE envelope (not Sigstore). Private key discarded after signing (α model).
  - **Caller**: tc_api `lifespan()` calls `init_chain("default")`. Multi-worker safe: 409 silently skipped.
  - **CCEL storage**: Only `SHA384(raw_CCEL)` digest stored. Non-TEE: null.
  - **Initialization semantics**: Logical state. Subsequent `/commit` calls proceed while Event Log 0 is PENDING. Baseline record uses `rtmr_extended=True` for submit daemon/crash recovery compat.
- **Acceptance Criteria**:
  1. ✅ tc_api generates ECDSA P-384 keypair at startup, creates Event Log 0, signs with TEE private key.
  2. ✅ Event Log 0 captures RTMR[2] snapshot (no extend) and CCEL digest as baseline entries.
  3. ✅ `pub_key` field populated with TEE-generated public key in PEM format.
  4. ✅ Event Log 0 committed via `POST /init-chain` and queued for Rekor submission.
  5. ✅ Subsequent `/commit` calls not blocked while Event Log 0 is pending.
  6. ✅ RTMR index corrected from `0` to `2` across all extend/read operations.
- **Tests**: `tests/test_init_chain.py` (12 tests), `tests/test_ccel.py` (6 tests); all passing
- **OpenSpec**: `openspec/changes/archive/2026-04-17-event-log-0-baseline/`

---

### ~~GAP-06: Granular Lifecycle States~~ ✅ COMPLETED

- **Priority**: MEDIUM
- **Scope**: `tc_api/trucon/app.py`, `tc_api/trucon/database.py`, `tc_api/tlog/types.py`
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

- **Priority**: ~~MEDIUM~~ → LOW (long-term)
- **Scope**: `tc_api/trucon/adapters/`
- **References**: ../../tlog/docs/trusted-log/architecture.md component diagram (OnChain implementation)
- **Dependencies**: External — requires a concrete on-chain target (EVM, Solana, custom, etc.) to be selected before implementation can begin.
- **Current State**: Only `SigstoreLogAdapter` (Rekor/transparent-log) exists. The `ImmutableLogAdapter` abstract interface is defined in `tc_api/tlog/immutable.py`, but no on-chain implementation exists. Blocked by target chain selection.
- **Acceptance Criteria**:
  1. `OnChainAdapter` class implementing `ImmutableLogAdapter`.
  2. `submit_bundle()`, `get_entry()`, `traverse()` implemented for on-chain target.
  3. Submit daemon can be configured to use on-chain backend (alongside or instead of Rekor).

---

### ~~GAP-08: Feature-Flag Fallback to Legacy Write Path~~ CLOSED (Won't Do)

- **Priority**: ~~MEDIUM~~ — CLOSED
- **Scope**: `tc_api/api/app.py`, `tc_api/api/runtime.py`, `tc_api/config.py`
- **References**: architecture.md §8.1, §11
- **Dependencies**: None
- **Closed**: 2026-04-17
- **Rationale**: The legacy direct-write path (`trusted_container_log` module) has been fully removed. RTMR extends are irreversible single-directional hardware accumulations — any fallback path that bypasses TruCon's serialized `threading.Lock` scope (RTMR extend + SQLite INSERT + chain state update) would break the RTMR hash chain, making the trust chain unverifiable. No fallback design can simultaneously preserve trust chain integrity, RTMR ordering, and replay capability. The current best-effort commit pattern in `commit_and_save_receipt()` already allows business operations (build/publish/launch) to succeed when TruCon is unavailable. TruCon availability should be ensured via process supervision (systemd/supervisord) rather than application-level fallback.

---

### ~~GAP-09: `prev_log_id` as DB-Level Ordering Verification (Non-TEE Mode)~~ ✅ COMPLETED

- **Priority**: MEDIUM
- **Scope**: `tc_api/trucon/app.py`
- **References**: ../../tlog/docs/trusted-log/architecture.md §"Non-TEE Mode: prev_log_id as DB-Level Ordering Verification"
- **Dependencies**: None
- **Completed**: 2026-04-17 | Archive: `openspec/changes/archive/2026-04-17-non-tee-verification/`
- **Design Decisions** (confirmed 2026-04-17):
  - `prev_log_id` stays OUT of the DSSE predicate (no signing change). This is DB-level verification, not cryptographic proof.
  - Unconfirmed chain tail: accepted as unverifiable (prev_log_id depends on log_id assignment at confirmation time).
  - Response model: keep existing `rtmr_available: bool` field, no new verification-mode field.
  - Startup behavior has since been tightened to TDX-only; missing RTMR extend support now fails startup.
  - Auto-detect only (via TDX sysfs presence). No explicit env var override.
- **Acceptance Criteria**:
  1. ✅ `verify-chain` checks `prev_log_id` linkage for confirmed records when `rtmr_available == False`.
  2. ✅ Historical note: the original change introduced a startup warning before the service was later tightened to TDX-only startup.
  3. ✅ No changes to signing flow, DSSE predicate format, or commit flow.
- **Tests**: `tests/test_non_tee_verification.py` (5 tests, all passing)

---

### ~~GAP-10: Internal Service Authentication (Phase A — Bearer Token)~~ ✅ COMPLETED

- **Priority**: MEDIUM
- **Scope**: `tc_api/trucon/app.py`, `tc_api/transparency/commit_client.py`, `tc_api/docktap/trucon_client.py`, `tc_api/config.py`
- **References**: architecture.md §9
- **Dependencies**: None
- **Completed**: 2026-04-17 | Archive: `openspec/changes/archive/2026-04-17-internal-service-auth/`
- **Design Decisions** (confirmed 2026-04-17):
  - Phase A: Shared Bearer token (`TRUCON_SERVICE_TOKEN` env var) for both tc_api and Docktap.
  - All TruCon endpoints authenticated via a single FastAPI middleware.
  - Token generated at CVM startup (`start.sh`), session-scoped (lifetime = VM lifetime).
  - `TRUCON_AUTH_DISABLED=true` dev-mode bypass with prominent startup warning.
  - 401 responses with descriptive JSON body for debugging.
  - Constant-time comparison via `hmac.compare_digest`.
  - Phase B follow-up was completed on 2026-04-19 in GAP-12 via UDS-first transport, caller identity, and minimal caller policy.
- **Acceptance Criteria**:
  1. ✅ TruCon endpoints require `Authorization: Bearer <token>` header.
  2. ✅ tc_api and Docktap attach credentials when calling TruCon.
  3. ✅ Unauthorized requests rejected with 401 + descriptive JSON.
  4. ✅ Dev-mode bypass for testing environments.
- **Tests**: `tests/test_service_auth.py` (9 tests); 102 total regression pass

---

### ~~GAP-12: Internal Service Authentication — Phase B (Unix Socket Peer Credentials / Caller Identity)~~ ✅ COMPLETED

- **Priority**: LOW
- **Scope**: `tc_api/trucon/app.py`, `tc_api/transparency/commit_client.py`, `tc_api/docktap/trucon_client.py`
- **References**: architecture.md §9; GAP-10 design notes
- **Dependencies**: GAP-10 ✅
- **Completed**: 2026-04-19 | Archive: `openspec/changes/archive/2026-04-19-harden-trucon-internal-auth/`
- **Implemented Outcome**:
  - TruCon now prefers a shared Unix domain socket transport for same-machine internal callers.
  - TruCon derives caller identity from Linux peer credentials and records caller metadata for audit and local status reporting.
  - Internal authorization now distinguishes at least `tc_api` and `docktap`, with Docktap kept commit-oriented by default.
  - Existing HTTP + Bearer-token wiring remains as a compatibility path only for transitional/internal healthcheck usage; UDS is the primary control-plane transport.
  - The refactor absorbed `FIX-03` and `FIX-05`, removing dead submit/status API surface during the transport hardening work.
- **Acceptance Criteria**:
  1. ✅ TruCon accepts same-machine internal traffic over a Unix domain socket and validates Linux peer credentials for admission.
  2. ✅ TruCon derives and records a caller identity that distinguishes at least `tc_api` and `docktap`.
  3. ✅ TruCon enforces a minimal caller policy matrix, with tc_api retaining full internal access and Docktap restricted to commit-oriented endpoints unless explicitly expanded.
  4. ✅ Existing HTTP + Bearer-token wiring is documented as transitional compatibility only while UDS is the default internal transport.
  5. ✅ Touched record/status contracts resolved `FIX-03` and `FIX-05` rather than carrying forward dead API surface.
- **Tests**: `tests/test_service_auth.py`, `tests/test_trucon_internal_transport.py`, `docktap/tests/test_docktap_integration.py`; broader regression suites passed during apply.

---

### ~~GAP-11: Historical Per-Workload Chain Assignment for Docktap~~ ✅ COMPLETED / SUPERSEDED

- **Priority**: MEDIUM
- **Scope**: `tc_api/docktap/`, `tc_api/trucon/`
- **References**: architecture.md §4.2, §7; Q-01
- **Dependencies**: GAP-01 ✅
- **Completed**: 2026-04-17 | Archive: `openspec/changes/archive/2026-04-17-per-workload-chain-assignment/`
- **Current State**: Superseded by the later default-only measured-chain rollback. The historical implementation routed Docktap events onto workload-scoped measured chains, but the active runtime model now commits all measured history to `chain_id="default"` and uses `workload_id` only for correlation.
- **Design Notes**: Container label convention (`--label io.trucon.workload-id=xxx`) is still extracted from `docker create` request body. Subsequent operations still resolve `workload_id` via Docktap's persisted mapping state, but that label no longer selects an independent measured chain.
- **Acceptance Criteria**:
  1. ✅ Docktap extracts `io.trucon.workload-id` from container labels during `create` operations.
  2. ✅ Historical implementation used the resolved `workload_id` as `chain_id` for workload-scoped measured chains before the later rollback.
  3. ✅ Current runtime behavior keeps measured commits on `"default"`; unlabeled containers still fall back to default correlation behavior.
  4. ✅ Tests cover label extraction, cross-operation workload resolution, and fallback behavior.
- **Tests**: `docktap/tests/test_workload_chain_routing.py`

---

### ~~GAP-20: Event Log 0 Baseline for Implicit Workload Chains~~ ✅ COMPLETED

- **Priority**: MEDIUM
- **Scope**: `tc_api/transparency/commit_client.py`, `tc_api/trucon/app.py`, `tc_api/docktap/trucon_client.py`, historical workload-chain verification/docs
- **References**: ../../tlog/docs/trusted-log/architecture.md §Event Log 0, §Trust Log Initialization Flow; architecture.md measured-chain model evolution
- **Dependencies**: GAP-05 ✅, GAP-11 ✅, GAP-17 ✅
- **Completed**: 2026-04-20 | Change: `openspec/changes/add-workload-chain-baseline/`
- **Current State**: Superseded by the later default-only measured-chain rollback. The active model keeps the explicit Event Log 0 bootstrap only for `default`, and workload identity remains signed metadata rather than a separate measured chain.
- **Implemented Outcome**: Historical workload-chain baseline work established explicit baseline semantics, but active runtime behavior now collapses all RTMR-backed history to `default`.
- **Acceptance Criteria**:
  1. ✅ Historical baseline behavior for workload-scoped chains was implemented before the later rollback.
  2. ✅ That earlier baseline creation path was idempotent and race-safe.
  3. ✅ The current runtime contract no longer exposes workload-scoped measured chains.
  4. ✅ Active documentation now treats workload identity as metadata within the default measured chain.

---

## Part B: Implementation Inconsistencies (Code Diverges from Architecture)

### ~~FIX-01: Digest Algorithm — Two-Level Hashing Not Implemented~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `tc_api/transparency/commit_client.py`
- **References**: ../../tlog/docs/trusted-log/architecture.md §Digest Algorithm
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
- **Scope**: `tc_api/trucon/app.py`, `tc_api/trucon/database.py`, `tc_api/transparency/commit_client.py`
- **References**: ../../tlog/docs/trusted-log/architecture.md §Data Structures
- **Completed**: 2026-04-17 | Archive: `openspec/changes/archive/2026-04-17-status-response-fix/`
- **Acceptance Criteria**:
  1. ✅ `GET /status` returns `CommitQueueStatusResponse` matching `CommitQueueStatus` contract (`has_queued_records`, `queued_record_count`, `next_record_id`) plus granular GAP-06 counts.
  2. ✅ New `GET /state` endpoint returns `LatestStateResponse` with `latest_confirmed_log_id`, `pending_event_ids[]`, `latest_mr_value` for default chain.
  3. ✅ `tlog_client.py` properly maps new field names and populates `next_record_id`.
  4. ✅ Old `QueueStatusResponse` model removed.
- **Tests**: `tests/test_status_response.py` (15 tests, all passing); 73 total regression pass

---

### ~~FIX-03: `SubmitResult` Type Defined but Never Exposed~~ ✅ COMPLETED

- **Priority**: LOW
- **Scope**: `tc_api/tlog/types.py`, `tc_api/trucon/app.py`
- **References**: ../../tlog/docs/trusted-log/architecture.md §Data Structures, §Message Flow step 4
- **Completed**: 2026-04-19 | Archive: `openspec/changes/archive/2026-04-19-harden-trucon-internal-auth/`
- **Implemented Outcome**: The unused `SubmitResult` type was removed during the GAP-12 refactor. No runtime endpoint exposed it, and the current queue-driven submit model does not produce or require a separate queryable submit-result contract.
- **Acceptance Criteria**:
  1. ✅ `SubmitResult` was removed instead of being exposed through a new endpoint.
  2. ✅ No dead submit-result contract remains in the public or internal type surface.

---

### FIX-04: Entry Type Too Narrow for Architecture's Rich Entry Schema — ✅ COMPLETED

- **Priority**: LOW
- **Scope**: `tlog/tlog/types.py`, `tc_api/transparency/commit_client.py`
- **References**: ../../tlog/docs/trusted-log/architecture.md §JSON Mock-Up
- **Completed**: 2026-04-18 | Archive: `openspec/changes/entry-value-native-json/`
- **Design Decisions** (confirmed 2026-04-18):
  - **Approach**: `Entry.value` widened from `str` to `Any` (JSON-compatible: str, int, float, bool, None, list, dict). The `key`/`value` wire format is retained; rich structured metadata is passed natively as dicts/lists.
  - **Digest stability**: `canonical_json()` (sort_keys=True, compact separators) already handles nested objects deterministically. No digest algorithm change needed.
  - **Docktap unification**: Docktap now imports `Entry` from `tc_api.tlog.types` instead of using raw tuples.
  - **JSON-in-JSON elimination**: All `json.dumps()` wrappers removed from `add_entry()` call sites in `api/workflows.py` and `services/`. DSSE predicates now contain native JSON values.
  - **Typo fix**: `"verfiy_sbom_status"` → `"verify_sbom_status"` bundled with this change.

---

## Part C: Deployment, Tooling & Documentation Gaps (Previously Untracked)

### ~~GAP-13: Docktap Deployment Integration~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `start.sh`, `tc-api/docker-compose.yml`, `tc-api/Dockerfile`, `docktap/main.py`
- **References**: architecture.md §4.2, §6.2, §10; docktap/architecture.md
- **Dependencies**: GAP-01 ✅, GAP-10 ✅, GAP-11 ✅
- **Completed**: 2026-04-17 | Archive: `openspec/changes/docktap-deployment-integration/`
- **Design Decisions** (confirmed 2026-04-17):
  - **Deployment topology**: Independent container (Docker Compose) + background process (`start.sh`). Same image as tc_api/trucon with different command override.
  - **Failure model**: Docktap down = Docker CLI unavailable (security: all operations must be recorded). `restart: unless-stopped` for auto-recovery.
  - **Health check**: HTTP `/healthz` endpoint on port 8002 via daemon thread in `SockBridge`.
  - **Token sharing**: Compose `.env` file + variable interpolation. Bare-metal: environment variable inheritance.
  - **Proxy socket**: Bind-mount `/var/run/docktap/` directory. Users set `DOCKER_HOST=unix:///var/run/docktap/docker.sock`.
- **Acceptance Criteria**:
  1. ✅ `tc-api/docker-compose.yml` includes `docktap` service with daemon socket mount, proxy socket volume, healthcheck, depends_on, and `TRUCON_SERVICE_TOKEN`.
  2. ✅ `start.sh` launches Docktap as managed background process with PID tracking and graceful shutdown.
  3. ✅ `Dockerfile` exposes port 8002 for health endpoint.
  4. ✅ Healthcheck configured via `curl -f http://localhost:8002/healthz`.
  5. ✅ `DOCKER_HOST` configuration and deployment instructions documented in README.md.
- **Tests**: Compose config validated (`docker compose config --services` lists all 4 services). 107 existing tests pass. Syntax checks pass for all modified files.

---

### ~~GAP-14: Chain Verification CLI Tool~~ ✅ COMPLETED

- **Priority**: MEDIUM
- **Scope**: `tc_api/cli/verify.py`, `tc_api/transparency/commit_client.py`, package metadata, verification docs
- **References**: ../../tlog/docs/trusted-log/architecture.md §Verification Plane; ../../tlog/docs/trusted-log/api.md `verify_record()`; architecture.md §6.3
- **Dependencies**: None
- **Completed**: 2026-04-18 | Archive: `openspec/changes/archive/2026-04-18-add-chain-verification-cli/`
- **Design Decisions** (confirmed 2026-04-18):
  - **Packaging**: Exposed as package console script `tc-verify`, not an ad hoc helper script.
  - **Target model**: Initial v1 exposed `chain_id` as the verification selector; later changes moved the supported external contract to exported attested-head evidence, with `chain_id` retained only for explicit troubleshooting mode.
  - **Verdict model**: Immutable-backend replay is the primary source; TruCon local verification is retained as secondary diagnostic input.
  - **Policy flags**: Supports `--signer-identity`, `--expected-entry-count`, `--fail-on-pending`, and `--require-tee`.
  - **TDX requirement**: Production verification is expected to run against TDX-backed attested-head evidence.
- **Acceptance Criteria**:
  1. ✅ CLI accepts a `chain_id` and performs Rekor traversal, digest replay, signature validation, and local RTMR diagnostics.
  2. ✅ Supports TDX-backed verification and evidence-driven workflows.
  3. ✅ Human-readable output with per-record detail and summary.
  4. ✅ Machine-readable JSON output option (`--json`).
  5. ✅ Documented in README.md, docs/TESTING.md, and trusted-log docs.

---

### ~~GAP-17: Attested Head Evidence Export~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `tc_api/trucon/`, quote/evidence production path, `../../tlog/docs/trusted-log/verification.md`
- **References**: architecture.md §6.4, §12; ../../tlog/docs/trusted-log/architecture.md §Operator Verification Surfaces; ../../tlog/docs/trusted-log/verification.md §Attested Head Evidence
- **Dependencies**: GAP-05 ✅, GAP-14 ✅
- **Completed**: 2026-04-19
- **Sizing**: Implemented across two archived changes; umbrella task now complete.
- **Current State**: Event Log 0 anchors the chain baseline in Rekor, and TruCon now exports a strict read-only attested-head evidence package for the latest confirmed public head via `GET /evidence`.
- **Suggested Subtasks**:
  1. ~~`GAP-17A` — Attested head evidence contract~~ ✅ COMPLETED
    - Completed: 2026-04-19 | Archive: `openspec/changes/archive/2026-04-19-attested-head-evidence-contract/`
    - Outcome: v1 evidence schema, quote-binding field set, canonical JSON contract, and validation fixtures are frozen.
  2. ~~`GAP-17B` — TruCon evidence export surface~~ ✅ COMPLETED
    - Completed: 2026-04-19 | Archive: `openspec/changes/archive/2026-04-19-export-attested-head-evidence/`
    - Outcome: TruCon exports the latest confirmed public head as a strict v1 attested-head evidence package with freshness fields, binding validation, and failure coverage for missing confirmed heads or quote/binding failures.
- **Acceptance Criteria**:
  1. ✅ Define and expose a read-only evidence package containing at least `chain_id`, `sequence_num`, `head_log_id`, `mr_value`, and `quote`.
  2. ✅ Evidence package explicitly associates attested state with the public Rekor chain head.
  3. ✅ Event Log 0 is treated as the epoch baseline anchor during evidence generation and verification.
  4. ✅ Documentation explains trust assumptions, evidence lifetime, and how exported evidence relates to Rekor replay.

---

### ~~GAP-18: tc-verify External Evidence Mode~~ ✅ COMPLETED

- **Priority**: HIGH
- **Scope**: `tc_api/cli/verify.py`, verification support code, package interfaces, tests
- **References**: ../../tlog/docs/trusted-log/verification.md §Verification Inputs, §Verification Flow; architecture.md §6.4
- **Dependencies**: GAP-14 ✅, GAP-17
- **Completed**: 2026-04-19 | Archive: `openspec/changes/archive/2026-04-19-tc-verify-external-evidence-mode/`
- **Sizing**: Implemented as one archived umbrella change after GAP-17 completed.
- **Current State**: `tc-verify` now uses exported attested-head evidence as its supported external operator input, validates replay-to-attested-head association, and retains live TruCon-backed verification only as explicit troubleshooting-only diagnostics.
- **Suggested Subtasks**:
  1. ~~`GAP-18A` — tc-verify evidence input mode~~ ✅ COMPLETED
    - Completed: 2026-04-19 | Archive: `openspec/changes/archive/2026-04-19-tc-verify-external-evidence-mode/`
    - Outcome: CLI accepts exported evidence as a first-class input and resolves replay targets from the package instead of requiring live `chain_state` discovery.
  2. ~~`GAP-18B` — Attested-head verification in tc-verify~~ ✅ COMPLETED
    - Completed: 2026-04-19 | Archive: `openspec/changes/archive/2026-04-19-tc-verify-external-evidence-mode/`
    - Outcome: CLI verifies replay-to-attested-head association and reports replay findings separately from attested-head diagnostics.
  3. ~~`GAP-18C` — Close external verifier boundary~~ ✅ COMPLETED
    - Completed: 2026-04-22 | Archive: `openspec/changes/archive/2026-04-22-close-external-verifier-boundary/`
    - Outcome: bare `chain_id` external verification is rejected; live TruCon verification now requires an explicit troubleshooting selector and is labeled as internal diagnostics in UX, JSON output, and docs.
- **Acceptance Criteria**:
  1. ✅ `tc-verify` can verify a chain using Rekor plus exported attested evidence, without requiring live TruCon connectivity.
  2. ✅ Live TruCon-backed verification remains available only as explicit troubleshooting mode and is not presented as the supported external verifier contract.
  3. ✅ CLI output distinguishes public replay results from attested-head evidence results.
  4. ✅ Tests cover remote-verifier mode, missing-evidence failures, and mismatched evidence-to-chain association.

---

### ~~GAP-19: Verification Profiles for Application Flows~~ ✅ COMPLETED

- **Priority**: MEDIUM
- **Scope**: event producers in `tc_api/`, `tc_api/docktap/`, `tc-verify` verification logic, trusted-log verification docs
- **References**: ../../tlog/docs/trusted-log/verification.md §Verification Profiles; architecture.md §6.1, §6.2
- **Dependencies**: GAP-14 ✅, GAP-18 ✅
- **Completed**: 2026-04-19 | Archive: `openspec/changes/archive/2026-04-19-add-verification-profiles/`
- **Current State**: Canonical application-layer verification profiles are now implemented end-to-end. The verifier reports independent verdicts for `build`, `publish`, `launch`, and `docktap-runtime`, and producers now emit the minimum identity and outcome fields required by those profiles.
- **Implemented Subtasks**:
  1. ~~`GAP-19A` — Verification profile contract~~ ✅ COMPLETED
    - Outcome: canonical profile contracts are frozen for `build`, `publish`, `launch`, and `docktap-runtime`.
    - Shared verdict states are now `verified`, `warning`, `incomplete`, and `failed`.
  2. ~~`GAP-19B` — Producer payload alignment~~ ✅ COMPLETED
    - Outcome: REST build/publish/launch flows emit profile-aligned audit fields such as `output_image_digest`, `dockerfile_digest`, `build_context_digest`, `base_image_digests`, `pushed_subject_digest`, `target_ref`, `launch_id`, `launch_config_digest`, and launch security projection fields.
    - Outcome: Docktap runtime commits now emit `operation_result`, workload/instance identity, image target identity, and `launch_id` when runtime events are attributable to a REST-originated launch flow.
  3. ~~`GAP-19C` — tc-verify profile enforcement~~ ✅ COMPLETED
    - Outcome: `tc-verify` evaluates profile-specific evidence sets, reports separate per-profile findings in text and JSON output, and evaluates the latest workload-scoped launch attempt by `launch_id`.
- **Design Decisions**:
  - `build` requires stable artifact and input identities; optional SBOM identity is warning-only.
  - `publish` remains intentionally simple in v1, but success without `pushed_subject_digest` and `target_ref` is a hard failure.
  - `launch_id` is reused as the v1 launch-attempt boundary; no separate `launch_attempt_id` was introduced.
  - `launch` requires both `launch_config_digest` and explicit security projection (`privileged`, `network_mode`, `mounts`, `devices`, `capabilities`) so the verifier can support both machine checks and human audit.
  - `docktap-runtime` requires explicit `operation_result` and conditional identity fields keyed to workload and container scope.
- **Acceptance Criteria**:
  1. ✅ Canonical verification profiles defined for `build`, `publish`, `launch`, and `docktap-runtime`.
  2. ✅ Each profile documents required fields, hard-fail conditions, and warning-only omissions.
  3. ✅ Event producers emit the minimum data required by the corresponding profile.
  4. ✅ `tc-verify` reports per-flow verdicts rather than inventing one global workload-lifecycle status.
- **Tests**: `tests/test_verification_profiles.py`, `tests/test_verify_cli.py`, `docktap/tests/test_trucon_client.py`, `docktap/tests/test_workload_store.py`, `docktap/tests/test_workload_chain_routing.py`; focused regression: 81 passed

---

### ~~GAP-15: Docktap In-Memory Retention / Garbage Collection~~ ✅ COMPLETED

- **Priority**: MEDIUM
- **Scope**: `docktap/main.py`, `docktap/proxy/operation_log.py`, `docktap/workload_store.py`, `tc_api/docktap/trucon_client.py`
- **References**: docktap/architecture.md §Data Model (`cleanup_old_operations(max_age_hours=24)`)
- **Dependencies**: GAP-13 ✅
- **Completed**: 2026-04-18 | Archive: `openspec/changes/archive/2026-04-18-docktap-local-state-retention-and-runbook-closure/`
- **Design Notes**:
  - **Sweeper model**: `docktap/main.py` starts a periodic local-state sweeper thread.
  - **Two-layer retention**: operation tracker entries, removed-container workload mappings, and resolved retry bookkeeping are cleaned independently.
  - **Replay boundary**: Docktap-local state is treated as bounded operational cache only; replay and verification remain dependent on TruCon and immutable backends.
  - **Configuration**: Retention windows and sweep interval are controlled via environment variables.
- **Acceptance Criteria**:
  1. ✅ Periodic cleanup of `OperationTracker` entries via Docktap background sweeper.
  2. ✅ Retention policy for removed-container `WorkloadStore` rows via `cleanup_removed()`.
  3. ✅ Resolved retry bookkeeping cleanup via `cleanup_resolved_submissions()`.
  4. ✅ Configurable retention parameters via environment variables (`DOCKTAP_GC_INTERVAL_SECONDS`, `DOCKTAP_OPERATION_RETENTION_HOURS`, `DOCKTAP_REMOVED_CONTAINER_RETENTION_HOURS`, `DOCKTAP_ACKED_RETRY_RETENTION_HOURS`, `DOCKTAP_TERMINAL_RETRY_RETENTION_HOURS`).
- **Tests**: `docktap/tests/test_workload_store.py`, `docktap/tests/test_trucon_client.py`

---

### ~~GAP-16: Architecture Documentation Sync~~ ✅ COMPLETED

- **Priority**: LOW
- **Scope**: `docs/architecture.md`, `../../tlog/docs/trusted-log/architecture.md`, `../../tlog/docs/trusted-log/api.md`, `docs/docktap/architecture.md`
- **References**: All completed GAP/FIX tasks
- **Dependencies**: None
- **Completed**: 2026-04-19
- **Current State**: The architecture docs have now been reconciled with the implemented verification boundary, profile-aware verifier behavior, and current producer payload contracts.
- **Acceptance Criteria**:
  1. ✅ Remaining stale "planned" / "pending" / outdated contract annotations updated to reflect completed status and current runtime behavior.
  2. ✅ File path references remain aligned with current module layout.
  3. ✅ Architecture narratives now show implemented Docktap, TruCon, evidence-export, and verification-profile flows.
  4. ✅ No functional changes to code.

---

### GAP-21: Runtime Observation Classification Expansion for Docktap

- **Priority**: MEDIUM
- **Scope**: `docktap/proxy/operation_log.py`, `docktap/proxy/docker_proxy.py`, `docktap/tests/`, `docs/docktap/architecture.md`, `docs/docktap/api.md`
- **References**: `docs/docktap/architecture.md` canonical request sequence and endpoint mapping sections; `docs/docktap/api.md` DockerProxyServer behavioral requirements; `openclaw-docker-analysis.md` Phase 1 / 8 / 10 analysis
- **Dependencies**: GAP-01 ✅, GAP-11 ✅, GAP-15 ✅
- **Current State**:
  - Docktap's canonical classifier explicitly recognizes `preflight_ping`, `preflight_info`, `image_inspect`, `pull`, `create`, `start`, `stop`, `wait`, `rm`, `rmi`, `inspect`, and `unknown`.
  - TruCon submission is intentionally restricted to `pull` / `create` / `start` / `stop` / `rm`; this task does **not** require expanding the trusted-event submission surface.
  - Several operationally meaningful Docker Engine API paths still collapse into `inspect` or `unknown`, which makes daemon/control-plane traces like the OpenClaw analysis harder to interpret.
- **Goal**: Expand the read-only observation model so normal Docker control-plane activity is classifiable and queryable without changing Docker API semantics or broadening TruCon commit scope.
- **Acceptance Criteria**:
  1. Docktap can distinguish runtime observation calls from core lifecycle commits rather than collapsing them into generic `inspect` / `unknown` buckets.
  2. Benign cache-miss / probe responses (especially `404`) can be represented as normal observation outcomes instead of looking like errors.
  3. New observation classes remain best-effort logging metadata only unless a later design explicitly promotes them into TruCon-submittable events.
  4. Docktap architecture/API docs and focused classifier tests stay aligned with the expanded observation taxonomy.

#### Task 21.1: Add explicit container-list observation classification

- **Priority**: HIGH
- **Scope**: `docktap/proxy/operation_log.py`, `docktap/tests/test_lifecycle_classification.py`, `docktap/tests/test_proxy.py`, docs mapping tables
- **Dependencies**: None
- **Completed**: 2026-04-28 | Archive: `openspec/changes/archive/2026-04-28-docktap-container-list-observation/`
- **Goal**: Classify `GET /v*/containers/json` requests as first-class observation events instead of leaving them implicit.
- **Acceptance Criteria**:
  1. `GET /v*/containers/json` is classified as a dedicated observation type such as `container_list`.
  2. Query parameters like `all=1` remain available in logged metadata for differentiating `docker ps` vs `docker ps -a` style scans.
  3. Existing lifecycle-parent linking rules remain unchanged for `create` / `start` / `stop` / `rm`.
  4. Focused classifier tests cover versioned and unversioned `/containers/json` paths.

#### Task 21.2: Add exec-path observation coverage

- **Priority**: HIGH
- **Scope**: `docktap/proxy/operation_log.py`, `docktap/proxy/docker_proxy.py`, `docktap/tests/`, docs mapping tables
- **Dependencies**: Task 21.1
- **Completed**: 2026-04-28 | Archive: `openspec/changes/archive/2026-04-28-docktap-exec-path-observation/`
- **Goal**: Represent command execution inside running containers as explicit observation events.
- **Acceptance Criteria**:
  1. `POST /v*/containers/{id}/exec` is classified separately from generic container inspect traffic.
  2. `POST /v*/exec/{id}/start` is classified separately from generic unknown traffic.
  3. Optional follow-up exec inspection paths are either explicitly classified or documented as intentionally deferred.
  4. Tests cover the minimal healthcheck-style flow: exec-create followed by exec-start.

#### Task 21.3: Split multi-resource probe traffic out of generic inspect/unknown buckets

- **Priority**: HIGH
- **Scope**: `docktap/proxy/operation_log.py`, response enrichment helpers, classifier tests, docs mapping tables
- **Dependencies**: Task 21.1
- **Completed**: 2026-04-28 | Archive: `openspec/changes/archive/2026-04-28-docktap-resource-probe-observation/`
- **Goal**: Make Docker's name/probe traffic readable in logs by distinguishing resource-specific lookup classes.
- **Acceptance Criteria**:
  1. Probe/inspect calls for at least container, network, volume, and plugin resources no longer collapse into the same generic fallback bucket.
  2. The logged metadata exposes which resource family was probed, either through distinct operation types or a stable `resource.kind` style field.
  3. Existing `image_inspect` behavior remains backward compatible.
  4. Tests cover common miss cases that mirror Docker's multi-resource name resolution pattern.

#### Task 21.4: Record benign observation outcomes for normal `404` misses

- **Priority**: MEDIUM
- **Scope**: `docktap/proxy/operation_log.py`, response enrichment helpers, tests, docs
- **Dependencies**: Task 21.2, Task 21.3
- **Completed**: 2026-04-28 | Archive: `openspec/changes/archive/2026-04-28-docktap-observation-miss-outcomes/`
- **Goal**: Distinguish expected probe misses from true proxy/runtime failures.
- **Acceptance Criteria**:
  1. Observation responses can encode at least `ok` / `miss` / `error` style outcomes or an equivalent stable scheme.
  2. Resource probes and image-inspect cache misses that return `404` are represented as normal misses rather than generic failures.
  3. Docker socket / timeout / malformed-request failures remain distinguishable from daemon-level `404` misses.
  4. Response-enrichment tests cover the normal-miss path explicitly.

#### Task 21.5: Reduce `unknown` noise for common runtime observation endpoints

- **Priority**: MEDIUM
- **Scope**: `docktap/proxy/operation_log.py`, `docktap/tests/`, `docs/docktap/architecture.md`, `docs/docktap/api.md`
- **Dependencies**: Task 21.2, Task 21.3
- **Completed**: 2026-04-28 | Archive: `openspec/changes/archive/2026-04-28-docktap-observation-unknown-reduction/`
- **Goal**: Capture remaining high-frequency read-only paths that are operationally useful but not part of the trusted lifecycle chain.
- **Acceptance Criteria**:
  1. At least `GET /v*/containers/{id}/logs` is promoted from `unknown` to an explicit observation class.
  2. Any intentionally deferred endpoints still left in `unknown` are called out in docs so the bucket becomes a conscious boundary rather than accidental overflow.
  3. `SUBMITTABLE_OPERATIONS` remains unchanged unless a separate future proposal decides otherwise.
  4. Documentation clearly separates lifecycle commit types from read-only observation types.

---

### GAP-22: Daemon-Internal Runtime Phase Observation for Docktap

- **Priority**: MEDIUM
- **Scope**: `docktap/`, `docs/docktap/architecture.md`, `docs/docktap/api.md`, runtime observability docs/runbooks
- **References**: `docker_daemon.log`; `openclaw-docker-analysis.md` Phase 4 / 6 / 7 / 8 / 9 analysis; Docktap architecture logging and proxy requirements
- **Dependencies**: GAP-21.2, GAP-21.3, GAP-21.4
- **Current State**:
  - Docktap's observation model is built around Docker Engine API requests and responses seen by the Unix-socket proxy.
  - Daemon-internal stages such as overlay mounts, OCI bundle creation, containerd task transitions, attach lifecycle, and healthcheck-internal execution are not represented as first-class observation artifacts.
  - Mixed traces like `docker_daemon.log` therefore contain two disconnected planes: API-path observations and daemon/runtime-internal phases.
- **Goal**: Define and incrementally add a second observation layer for daemon/runtime-internal phases so mixed Docker traces can be interpreted as one coherent timeline.
- **Acceptance Criteria**:
  1. The docs define a stable taxonomy for daemon/runtime-internal phases distinct from HTTP API request classes.
  2. Internal phase events can be correlated with the API request or container/exec object they belong to.
  3. Healthcheck and exec-related daemon activity can be interpreted without confusing it with primary workload lifecycle traffic.
  4. The new internal-phase layer remains observational/runbook-focused unless a later design adds a concrete event source and ingestion path.

#### Task 22.1: Define a daemon-internal phase taxonomy

- **Priority**: HIGH
- **Scope**: `docs/docktap/architecture.md`, `docs/docktap/api.md`, `docs/overview_tasks.md`
- **Dependencies**: None
- **Completed**: 2026-04-28 | Archive: `openspec/changes/archive/2026-04-28-docktap-daemon-phase-taxonomy/`
- **Goal**: Separate Docker Engine API observations from daemon/runtime-internal phases in the documentation model.
- **Acceptance Criteria**:
  1. The docs define a stable internal taxonomy for at least storage/mount, runtime-spec/bundle, task lifecycle, attach/stream, and housekeeping phases.
  2. The taxonomy explicitly states that these are not inferred from the current HTTP proxy path classifier alone.
  3. Internal phases are described as complementary to, not replacements for, API request observations.
  4. Example mappings from `docker_daemon.log` illustrate the taxonomy with real phase names.

#### Task 22.2: Normalize containerd task events into an observation model

- **Priority**: HIGH
- **Scope**: runtime observation docs, potential future parser/adapter contracts, tests for normalization rules if an ingestion surface is introduced
- **Dependencies**: Task 22.1
- **Completed**: 2026-04-28 | Archive: `openspec/changes/archive/2026-04-28-docktap-containerd-task-normalization/`
- **Goal**: Define a documentation-first normalized task-transition contract so containerd task activity is treated as structured daemon/internal observations rather than unstructured free-text debug lines.
- **Acceptance Criteria**:
  1. The model distinguishes at least `tasks/create`, `tasks/start`, `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit`.
  2. The docs define the minimum canonical daemon/internal facts for those transitions, including topic, timestamp, source namespace, container identity, and exec identity when available.
  3. Task transitions are explicitly separated from higher-level Docker API operations such as `create`, `start`, and exec API calls, while container-task and exec-task transitions remain distinguishable inside the same `task lifecycle` family.
  4. The normalization rules call out which transitions are required for cold-start analysis versus which remain supplemental for richer runtime interpretation.
  5. The docs state explicitly that API/internal correlation, healthcheck interpretation, attach-stream semantics, and parser or ingestion implementation remain out of scope for this task.

#### Task 22.3: Correlate API-path events with daemon-internal phases

- **Priority**: HIGH
- **Scope**: observation model docs, future parser contract notes, runbook examples
- **Dependencies**: Task 22.2
- **Completed**: 2026-04-28 | Archive: `openspec/changes/archive/2026-04-28-docktap-api-internal-correlation/`
- **Goal**: Define a documentation-first correlation contract so API-path observations and normalized daemon/internal transitions can be read as one mixed-trace timeline without collapsing parser design, healthcheck interpretation, or attach semantics into the same task.
- **Acceptance Criteria**:
  1. The docs specify the primary correlation shapes for `POST /containers/create`, `POST /containers/{id}/start`, and exec-path API observations against normalized daemon/internal transitions.
  2. The docs distinguish stronger identifiers from contextual evidence and fallback heuristics when describing cross-plane joins.
  3. The docs allow one-to-many, many-to-one, inferred, and unresolved correlation outcomes when trace evidence is incomplete.
  4. The docs state explicitly that parser implementation, healthcheck intent, attach-stream semantics, and housekeeping guidance remain out of scope for this task.

#### Task 22.4: Model healthcheck and attach flows as secondary runtime activity

- **Priority**: MEDIUM
- **Scope**: observation docs/runbooks, future parser contract notes
- **Dependencies**: Task 22.2, Task 22.3
- **Completed**: 2026-04-28 | Archive: `openspec/changes/archive/2026-04-28-docktap-healthcheck-attach-interpretation/`
- **Goal**: Define a documentation-first interpretation contract so healthcheck-like exec flows and attach activity can be read as secondary runtime activity without collapsing parser design or housekeeping guidance into the same task.
- **Acceptance Criteria**:
  1. The docs define secondary runtime activity for healthcheck-like exec flows using the normalized exec-task spine and allow conservative interpretation when evidence is incomplete.
  2. Attach lifecycle lines (`stdout/stderr begin/end`, `attach done`) are described as stream/transport context around exec flows, not workload lifecycle events.
  3. The docs define a first-wave healthy healthcheck-like sequence with required exec-task evidence and separate contextual evidence.
  4. The docs define only the minimal anomalous secondary-runtime patterns worth surfacing later, such as repeated exec failures or missing exit/attach completion cues, while keeping housekeeping guidance out of scope.

#### Task 22.5: Add housekeeping/internal-maintenance phase coverage

- **Priority**: MEDIUM
- **Scope**: observation docs/runbooks, future parser contract notes
- **Dependencies**: Task 22.1, Task 22.3
- **Goal**: Define a documentation-first first-wave housekeeping interpretation contract so daemon/internal maintenance lines can be read as post-runtime context without collapsing them into secondary runtime activity or Docktap-local retention/GC behavior.
- **Acceptance Criteria**:
  1. First-wave housekeeping lines such as exec cleanup are modeled separately from primary lifecycle activity, secondary runtime activity, and Docktap-local retention/GC concerns.
  2. The docs describe the minimal first-wave boundary between expected maintenance noise and investigation-worthy housekeeping patterns.
  3. The first-wave model stays centered on exec-cleanup-style evidence while leaving room for later additions like image GC, background scanning, or retry/reconcile loops without redefining the taxonomy.
  4. Mixed-trace examples show where housekeeping phases sit relative to nearby primary runtime and secondary runtime events.

---

### ~~FIX-05: `SubmitStatus.OPEN` Enum Value Dead Code~~ ✅ COMPLETED

- **Priority**: LOW
- **Scope**: `tc_api/tlog/types.py`
- **References**: architecture.md §5.1; GAP-06 acceptance criteria §4 ("deferred until pre-commit assembly flow")
- **Dependencies**: None
- **Completed**: 2026-04-19 | Archive: `openspec/changes/archive/2026-04-19-harden-trucon-internal-auth/`
- **Implemented Outcome**: `SubmitStatus.OPEN` was removed during the GAP-12 cleanup. The current record assembly flow remains in-memory and does not require a persisted pre-commit OPEN lifecycle state.
- **Acceptance Criteria**:
  1. ✅ `OPEN` was removed from `SubmitStatus`.
  2. ✅ No replacement pre-commit assembly feature was introduced; the undocumented dead state is no longer part of the contract.

---

## Part D: Open Architecture Questions (Unresolved in Code)

_Renamed from former Part C._

These are not implementation tasks but **design decisions** that should be resolved before certain GAP tasks can proceed.

| ID | Question | Blocks | Architecture Ref | Status |
|----|----------|--------|------------------|--------|
| Q-01 | Chain scope default: per workload, per tenant, or global? | GAP-03 | architecture.md §12 | **Resolved** (updated 2026-06-01): global/default measured chain for tc_api and Docktap commits. `workload_id` remains a signed metadata dimension for correlation; GAP-11 is retained as historical work later superseded by the default-only rollback. |
| Q-02 | Confirmation SLA target from commit to backend confirmed? | GAP-04 | architecture.md §12 | Open |
| Q-03 | Canonical mandatory fields for stable instance mapping across restarts? | GAP-03 | architecture.md §12 | **Resolved** (2026-04-17): `instance_id` = full 64-char Docker `container_id`. One `create→rm` lifecycle = one instance. No cross-restart identity — that's `workload_id`'s role. |
| Q-04 | Worker ownership model: local ownership or shared lease? | — | architecture.md §12 | Open |
| Q-06 | Which quote-backed fields are mandatory to bind the current chain head to the current CVM state? | GAP-18B | architecture.md §12; ../../tlog/docs/trusted-log/verification.md §Attested Head Evidence | **Resolved** (2026-04-19): v1 binding covers `chain_id`, `sequence_num`, `head_log_id`, and `mr_value`. `expected_value` is computed by TruCon from canonical serialization of those bound fields and then compared against quote-backed report data; it is not derived from the quote itself. |
| Q-05 | How to handle runtimes that allow quote/report reads but not MR extend? | GAP-05 | ../../tlog/docs/trusted-log/architecture.md §Trust Log Initialization | **Resolved** (2026-04-17): Out of scope. Only TDX RTMR[2] is supported. AMD SEV-SNP and quote-only runtimes are not targeted. |

---

## Dependency Graph

```
GAP-01 (Docktap → TruCon, v1 default chain) ✅
  │
  ├──▶ GAP-11 (Historical per-workload chain assignment) ✅
  │         │
  │         ▼
  │    Q-01 ✅ ────┐
  │    Q-03 ✅ ────┼──▶ GAP-03 (Mapping Model) ✅
  │               │
  └───────────────┘

GAP-01 ✅ + GAP-10 ✅ + GAP-11 ✅ ──▶ GAP-13 (Docktap Deployment) ✅ ──▶ GAP-15 (Retention/GC) ✅

GAP-05 (Event Log 0) ✅ ── standalone (Q-05 resolved: TDX RTMR[2] only)
GAP-07 (On-Chain Adapter) ── standalone (blocked: target chain selection)
GAP-08 (Feature-Flag Fallback) ── CLOSED (Won't Do)
GAP-09 (Non-TEE Ordering) ✅ ── standalone
GAP-10 (Service Auth Phase A) ✅ ── standalone
GAP-11 (Historical per-workload chain) ✅
GAP-12 (Service Auth Phase B: UDS + caller identity) ✅ ◀── GAP-10 ✅
GAP-14 (Verification CLI) ✅ ── standalone
GAP-17 (Attested Head Evidence Export) ✅ ── umbrella complete
  ├──▶ GAP-17A (Evidence Contract) ✅
  └──▶ GAP-17B (Evidence Export Surface) ✅ ◀── GAP-17A ✅
GAP-18 (tc-verify External Evidence Mode) ✅ ── umbrella complete
  ├──▶ GAP-18A (Evidence Input Mode) ✅ ◀── GAP-17B ✅
  ├──▶ GAP-18B (Attested-Head Verification) ✅ ◀── GAP-18A ✅, Q-06 ✅
  └──▶ GAP-18C (Fallback Demotion) ✅ ◀── GAP-18B ✅
GAP-19 (Verification Profiles) ✅ ── umbrella complete
  ├──▶ GAP-19A (Profile Contract) ✅ ◀── GAP-18C ✅
  ├──▶ GAP-19B (Producer Payload Alignment) ✅ ◀── GAP-19A ✅
  └──▶ GAP-19C (tc-verify Profile Enforcement) ✅ ◀── GAP-19A ✅, GAP-19B ✅
GAP-20 (Historical workload-chain Event Log 0 baseline) ✅ ◀── GAP-05 ✅, GAP-11 ✅, GAP-17 ✅
GAP-21 (Docktap observation classification expansion)
  ├──▶ GAP-21.1 (container list classification) ✅
  ├──▶ GAP-21.2 (exec path coverage) ✅ ◀── GAP-21.1 ✅
  ├──▶ GAP-21.3 (resource probe split) ✅ ◀── GAP-21.1 ✅
  ├──▶ GAP-21.4 (benign 404 outcome semantics) ✅ ◀── GAP-21.2 ✅, GAP-21.3 ✅
  └──▶ GAP-21.5 (unknown-bucket noise reduction) ✅ ◀── GAP-21.2 ✅, GAP-21.3 ✅
GAP-22 (daemon-internal runtime phase observation)
  ├──▶ GAP-22.1 (phase taxonomy) ✅
  ├──▶ GAP-22.2 (containerd task normalization) ✅ ◀── GAP-22.1 ✅
  ├──▶ GAP-22.3 (API/internal correlation rules) ✅ ◀── GAP-22.2 ✅
  ├──▶ GAP-22.4 (healthcheck and attach modeling) ✅ ◀── GAP-22.2 ✅, GAP-22.3 ✅
  └──▶ GAP-22.5 (housekeeping phase coverage) ✅ ◀── GAP-22.1 ✅, GAP-22.3 ✅
GAP-16 (Doc Sync) ✅ ── standalone complete

FIX-03 (SubmitResult) ✅ ── completed with GAP-12
FIX-04 (Entry Type) ✅ ── completed
FIX-05 (OPEN Dead Code) ✅ ── completed with GAP-12

✅ DONE: GAP-02, FIX-01, GAP-06, FIX-02, GAP-04, GAP-09, GAP-01, GAP-10, GAP-11, GAP-03, GAP-05, FIX-04, GAP-12, FIX-03, FIX-05, GAP-13, GAP-14, GAP-15, GAP-16, GAP-17, GAP-18, GAP-19, GAP-20
✗ CLOSED: GAP-08
```

---

## Suggested Execution Order

**Phase 1 — Fix inconsistencies & foundational gaps** ✅ COMPLETE:
1. ~~`FIX-01`~~ ✅ completed 2026-04-16
2. ~~`GAP-02`~~ ✅ completed 2026-04-16
3. ~~`GAP-06`~~ ✅ completed 2026-04-16
4. ~~`FIX-02`~~ ✅ completed 2026-04-17

**Phase 2 — Core infrastructure** ✅ COMPLETE:
5. ~~`GAP-04`~~ ✅ completed 2026-04-17
6. ~~`GAP-05`~~ ✅ completed 2026-04-17 — Event Log 0 / baseline record
7. ~~`GAP-09`~~ ✅ completed 2026-04-17

**Phase 3 — Docktap Integration** ✅ COMPLETE:
8. ~~`GAP-01`~~ ✅ completed 2026-04-17
9. ~~`GAP-11`~~ ✅ completed 2026-04-17
10. ~~`GAP-03`~~ ✅ completed 2026-04-17
11. ~~`GAP-10`~~ ✅ completed 2026-04-17 (Phase A — Bearer token)

**Phase 4 — Trust chain completion** ✅ COMPLETE:
12. ~~`GAP-05`~~ ✅ completed 2026-04-17 — Event Log 0 / baseline record

**Phase 5 — Deployment & Operational Tooling**:
13. ~~`GAP-13`~~ ✅ completed 2026-04-17 — Docktap deployment integration
14. ~~`GAP-14`~~ ✅ completed 2026-04-18 — Chain verification CLI tool
15. ~~`GAP-15`~~ ✅ completed 2026-04-18 — Docktap local-state retention / garbage collection

**Phase 6 — Remote Verification Completion**:
16. ~~`GAP-17A`~~ ✅ completed 2026-04-19 — Attested head evidence contract
17. ~~`GAP-17B`~~ ✅ completed 2026-04-19 — TruCon evidence export surface
18. ~~`GAP-18A`~~ ✅ completed 2026-04-19 — tc-verify evidence input mode
19. ~~`GAP-18B`~~ ✅ completed 2026-04-19 — Attested-head verification in tc-verify
20. ~~`GAP-18C`~~ ✅ completed 2026-04-22 — Close external verifier boundary
21. ~~`GAP-19A`~~ ✅ completed 2026-04-19 — Verification profile contract
22. ~~`GAP-19B`~~ ✅ completed 2026-04-19 — Producer payload alignment
23. ~~`GAP-19C`~~ ✅ completed 2026-04-19 — tc-verify profile enforcement

**Phase 7 — Cleanup & Extensions**:
24. ~~`FIX-03`~~ ✅ completed 2026-04-19 — removed dead `SubmitResult` during GAP-12
25. ~~`FIX-05`~~ ✅ completed 2026-04-19 — removed dead `SubmitStatus.OPEN` during GAP-12
26. ~~`GAP-16`~~ ✅ completed 2026-04-19 — Architecture documentation sync
27. `GAP-07` — On-chain backend adapter (blocked: target chain selection)
28. ~~`GAP-08`~~ — CLOSED (Won't Do): legacy path removed, RTMR chain integrity prevents viable fallback
29. ~~`GAP-12`~~ ✅ completed 2026-04-19 — Service auth Phase B (Unix socket peer credentials / caller identity)
30. ~~`GAP-20`~~ ✅ completed 2026-04-20 — Historical workload-chain baseline work, later superseded by the default-only measured-chain rollback

**Phase 8 — Runtime Observation Model Closure**:
31. ~~`GAP-21.1`~~ ✅ completed 2026-04-28 — Explicit container-list observation classification
32. ~~`GAP-21.2`~~ ✅ completed 2026-04-28 — Exec-path observation coverage
33. ~~`GAP-21.3`~~ ✅ completed 2026-04-28 — Multi-resource probe classification split
34. ~~`GAP-21.4`~~ ✅ completed 2026-04-28 — Benign `404` observation outcome semantics
35. ~~`GAP-21.5`~~ ✅ completed 2026-04-28 — Unknown-bucket reduction for common observation endpoints

**Phase 9 — Daemon/Internal Trace Model Closure**:
36. ~~`GAP-22.1`~~ ✅ completed 2026-04-28 — Daemon-internal phase taxonomy
37. ~~`GAP-22.2`~~ ✅ completed 2026-04-28 — Containerd task-event normalization
38. ~~`GAP-22.3`~~ ✅ completed 2026-04-28 — API-path to internal-phase correlation rules
39. ~~`GAP-22.4`~~ ✅ completed 2026-04-28 — Healthcheck and attach-flow modeling
40. ~~`GAP-22.5`~~ ✅ completed 2026-04-28 — Housekeeping/internal-maintenance phase coverage

---

## Part E: Current Remaining Work Snapshot

The items below are the primary tasks that remain genuinely open after reconciling this table with the live code and archived changes:

Update (2026-04-20, historical): `GAP-20` completed before the later default-only measured-chain rollback. At that point workload chains shared the same explicit Event Log 0 origin semantics as the startup-initialized `default` chain; the active runtime model has since collapsed measured history back to `default`.

Update (2026-04-28): Added `GAP-21` as a documentation-first breakdown for expanding Docktap's read-only runtime observation taxonomy without widening TruCon submission scope. The five sub-tasks are intended to map cleanly onto future OpenSpec propose/apply changes.

Update (2026-04-28): `GAP-21.1` is now complete and archived as `openspec/changes/archive/2026-04-28-docktap-container-list-observation/`. Docktap now classifies `GET /containers/json` as `container_list` while keeping query metadata and lifecycle submission boundaries unchanged.

Update (2026-04-28): `GAP-21.2` is now complete and archived as `openspec/changes/archive/2026-04-28-docktap-exec-path-observation/`. Docktap now classifies `POST /containers/{id}/exec` as `exec_create` and `POST /exec/{id}/start` as `exec_start`, retains minimal exec-path identifiers, and keeps exec traffic outside lifecycle submission and parent-linking.

Update (2026-04-28): `GAP-21.3` is now complete and archived as `openspec/changes/archive/2026-04-28-docktap-resource-probe-observation/`. Docktap now classifies network, volume, and plugin read-only probe paths as `network_inspect`, `volume_inspect`, and `plugin_inspect`, while preserving `image_inspect` and container-detail `inspect` behavior and deferring benign `404` miss semantics to `GAP-21.4`.

Update (2026-04-28): `GAP-21.4` is now complete and archived as `openspec/changes/archive/2026-04-28-docktap-observation-miss-outcomes/`. Docktap now records stable local `response.outcome` values for selected probe-style observations, treats daemon `404` misses as benign `miss` cases for the explicit probe classes, and keeps TruCon lifecycle result semantics unchanged.

Update (2026-04-28): `GAP-21.5` is now complete and archived as `openspec/changes/archive/2026-04-28-docktap-observation-unknown-reduction/`. Docktap now classifies `GET /containers/{id}/logs` as `container_logs` and documents the remaining `unknown` bucket as an intentional deferred boundary for unmapped read-only endpoints.

Update (2026-04-28): Added `GAP-22` as the companion breakdown for daemon/containerd/internal-phase observability that sits above raw Docker Engine API path classification. These tasks are intended for mixed-trace analysis like `docker_daemon.log`, not just proxy-path enrichment.

Update (2026-04-28): `GAP-22.1` is now complete and archived as `openspec/changes/archive/2026-04-28-docktap-daemon-phase-taxonomy/`. Docktap now documents a second daemon/internal observation plane with five stable top-level phase families and explicit defer boundaries for later normalization, correlation, healthcheck, and housekeeping work.

Update (2026-04-28): `GAP-22.2` is now complete and archived as `openspec/changes/archive/2026-04-28-docktap-containerd-task-normalization/`. Docktap now documents a normalized containerd task-transition contract with first-wave transition coverage, minimum canonical daemon/internal facts, and a narrow defer boundary that keeps API/internal correlation and healthcheck interpretation in later GAP-22 tasks.

Update (2026-04-28): `GAP-22.3` is now complete and archived as `openspec/changes/archive/2026-04-28-docktap-api-internal-correlation/`. Docktap now documents a first-wave API/internal correlation contract with separate create/start and exec-path join shapes, tiered evidence rules, and explicit defer boundaries that keep healthcheck intent, attach semantics, and housekeeping guidance for later GAP-22 work.

Update (2026-04-28): `GAP-22.4` is now complete and archived as `openspec/changes/archive/2026-04-28-docktap-healthcheck-attach-interpretation/`. Docktap now documents a first-wave secondary-runtime interpretation contract for healthcheck-like exec flows and attach activity, keeps the normalized exec-task spine as the required runtime sequence, and defers housekeeping cleanup guidance to `GAP-22.5`.

Update (2026-04-28): `GAP-22.5` is now complete and archived as `openspec/changes/archive/2026-04-28-docktap-housekeeping-maintenance-coverage/`. Docktap now documents a first-wave housekeeping interpretation contract for post-runtime maintenance context, keeps the first wave anchored on exec-cleanup-style evidence, distinguishes daemon housekeeping from Docktap-local retention/GC behavior, and leaves broader maintenance families as future extension room.

- `GAP-07` — on-chain backend adapter, still blocked by target chain selection
