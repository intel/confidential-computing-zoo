## Context

The current `TrustedLogAPI` class in `trusted_container_log/api.py` is a monolithic component that owns chain state in process-local memory, performs Sigstore DSSE signing, extends RTMR hardware registers, and inserts into the SQLite commit queue — all within a single `commit_record()` call path. When `tc_api` is deployed with `uvicorn --workers 4`, each forked worker gets an independent copy of `_records`, `_entries`, and `_latest_confirmed_log_id`, producing siloed state and race conditions on both the RTMR device and SQLite write path.

A standalone `tlog_daemon.py` process polls the SQLite queue independently, creating duplicate-submit risks and startup ordering issues.

The system must support multi-worker `tc_api` for throughput while guaranteeing that RTMR extends and chain state updates are strictly serialized.

## Goals / Non-Goals

**Goals:**
- Eliminate all six concurrency bugs identified in the multi-worker analysis (state silos, RTMR races, non-atomic commit, double-submit, broken prev_log_id chain, duplicate daemons).
- Achieve atomic RTMR-extend + SQLite-insert within a single lock acquisition.
- Allow `tc_api` to scale horizontally (`--workers N`) without chain-safety concerns.
- Embed the submit daemon inside the Trust API process to eliminate deployment ordering and duplicate-instance problems.
- Maintain the three-layer trust model: DSSE (authenticity), RTMR (ordering), Rekor (public auditability).

**Non-Goals:**
- Multi-instance Trust API or distributed locking (Trust API is explicitly single-process).
- On-chain or blockchain integration (Rekor transparent log only).
- Changes to the Sigstore signing flow itself (still uses `sigstore-python` with offline mode).
- Dead letter queue for failed records (failed records stay in-table with `FAILED` status).
- Changes to the ephemeral `/dev/shm` storage location or DAC permission model.

## Decisions

### 1. Split Architecture: Stateless tc_api + Single-Instance Trust API

**Decision**: Separate the write-side (signing) from the sequence-side (RTMR + queue) into two distinct services communicating via REST.

**Rationale**: `threading.Lock()` is process-local; it cannot serialize across forked Uvicorn workers. Only a separate single-process service can guarantee serialized access to the RTMR device and chain state. REST was chosen over Unix domain sockets or shared-memory IPC for debuggability, standard tooling, and the co-maintainer's explicit preference.

**Alternatives considered**:
- Single-worker tc_api (`--workers 1`): Eliminates concurrency bugs but sacrifices throughput for all endpoints, not just the commit path.
- File-based advisory locking (`fcntl.flock`): Serializes RTMR access across processes but cannot atomically couple RTMR extend with SQLite INSERT and in-memory chain state update.
- Redis or external queue: Adds deployment dependency and operational complexity for a problem solvable with process-internal locking.

### 2. Signing in tc_api, Sequencing in Trust API

**Decision**: tc_api performs Sigstore DSSE signing (Fulcio certificate exchange + envelope construction) and sends the signed bundle to Trust API. Trust API performs RTMR extend + SQLite INSERT + chain state update behind a `threading.Lock()`.

**Rationale**: Signing requires the caller's OIDC identity token and is CPU/network-bound (Fulcio round-trip). Placing it outside the lock minimizes lock hold time. The lock protects only the fast local operations: one RTMR sysfs write (~µs), one SQLite INSERT (~ms), and one chain_state UPDATE (~ms).

**Lock scope**:
```
tc_api worker                          Trust API (single process)
─────────────                          ──────────────────────────
1. Receive request
2. Build DSSE predicate (no prev_log_id)
3. Sign with Sigstore (offline mode)
4. POST /commit {bundle, chain_id}  →  5. Acquire threading.Lock()
                                        6. Read chain_state → prev_log_id, sequence_num
                                        7. RTMR extend(digest)
                                        8. INSERT into commit_queue (rtmr_extended=TRUE)
                                        9. UPDATE chain_state (new head)
                                       10. Release lock
                                    ←  11. Return {record_id, mr_value, sequence_num}
```

### 3. Remove prev_log_id from DSSE Predicate

**Decision**: `prev_log_id` is maintained by Trust API in SQLite only. It is not included in the DSSE predicate that the caller signs.

**Rationale**: Including `prev_log_id` in the signed payload creates a three-way contradiction:
1. The API caller signs the DSSE envelope (they hold the identity token).
2. `prev_log_id` is system-maintained (only Trust API knows the current chain head).
3. The signed payload must be immutable after signing.

Removing it from the signature is safe because ordering is proven by the RTMR hardware chain (each extend incorporates the previous register value), not by a signed field. `prev_log_id` in SQLite provides a queryable chain for the submit daemon and verification, without needing cryptographic binding in the envelope.

### 4. Embedded Submit Daemon as Background Thread

**Decision**: The submit daemon runs as a `threading.Thread(daemon=True)` inside the Trust API process, started during FastAPI lifespan.

**Rationale**: A separate daemon process (`tlog_daemon.py`) has no coordination with the Trust API's lock and introduces startup ordering, PID management, and duplicate-instance risks. An in-process thread shares the same `threading.Lock()` scope and `chain_state` access, and its lifecycle is tied to the Trust API process.

**Behavior**:
- Polls `commit_queue` every 5 seconds for records with `status=PENDING` and `rtmr_extended=TRUE`.
- Submits to Rekor in `sequence_num` order (ascending).
- On success: updates status to `CONFIRMED`, sets `confirmed_at`.
- On failure: increments `retry_count`. After 10 retries, sets status to `FAILED`.
- `FAILED` records block subsequent Rekor submissions (to preserve ordering) but do not block new RTMR extends/commits.

### 5. Expanded SQLite Schema

**commit_queue table**:
```sql
CREATE TABLE IF NOT EXISTS commit_queue (
    record_id    TEXT PRIMARY KEY,
    event_id     TEXT,
    chain_id     TEXT NOT NULL,
    payload      TEXT NOT NULL,
    status       TEXT NOT NULL,           -- PENDING | CONFIRMED | FAILED
    rtmr_extended BOOLEAN DEFAULT FALSE,
    log_id       TEXT,                    -- Rekor log entry ID once confirmed
    prev_log_id  TEXT,                    -- Chain link (system-maintained)
    mr_value     TEXT,                    -- RTMR value after extend
    sequence_num INTEGER NOT NULL,        -- Monotonic within chain
    retry_count  INTEGER DEFAULT 0,
    confirmed_at TEXT,
    updated_at   TEXT NOT NULL
);
```

**chain_state table** (one row per chain_id):
```sql
CREATE TABLE IF NOT EXISTS chain_state (
    chain_id       TEXT PRIMARY KEY,
    head_record_id TEXT,                  -- Latest committed record_id
    head_log_id    TEXT,                  -- Latest confirmed Rekor log_id
    sequence_num   INTEGER DEFAULT 0,     -- Current sequence counter
    mr_value       TEXT,                  -- Current RTMR register value
    updated_at     TEXT NOT NULL
);
```

### 6. Crash Recovery with rtmr_extended Flag

**Decision**: On Trust API startup, scan `commit_queue` for crash-recovery logic:
- Records with `rtmr_extended=TRUE` and `status=PENDING`: Resume Rekor submission (the RTMR extend already happened; the signed bundle is valid).
- Records with `rtmr_extended=FALSE`: Discard (the RTMR was not extended; on VM restart the register has reset, making the bundle cryptographically orphaned).
- Rebuild `chain_state` from the highest `sequence_num` record with `rtmr_extended=TRUE`.

**Rationale**: The `rtmr_extended` flag is set inside the lock, immediately after the sysfs write succeeds. If the process crashes between RTMR extend and SQLite INSERT, the record is lost — but this is acceptable because the RTMR value has diverged and the next commit will incorporate the correct cumulative register state. The flag distinguishes "hardware committed" from "software only" records.

### 7. Single-Instance Enforcement

**Decision**: Trust API acquires an exclusive file lock (`fcntl.flock(LOCK_EX | LOCK_NB)`) on a well-known path (e.g., `/dev/shm/tc_api_queue/trust-api.lock`) at startup. If the lock is held, the process exits with a clear error.

**Rationale**: `threading.Lock()` only serializes within one process. A second Trust API instance would bypass the lock entirely, reintroducing all concurrency bugs. File locking is the simplest cross-process exclusion mechanism and works on tmpfs.

### 8. Verification via chain_id + Signer Identity

**Decision**: When verifying a chain's entries in Rekor, query by `chain_id` (from the DSSE predicate's subject name) and filter by the Trust API's signer identity (Fulcio certificate identity).

**Rationale**: Rekor is a public append-only log; anyone can submit entries. An attacker could inject entries with a matching `chain_id` to cause DoS on verification (extra entries to process). Filtering by signer identity (the Trust API's workload identity) eliminates injected entries because the attacker cannot forge Fulcio certificates for the legitimate identity.

## Risks / Trade-offs

- **[Single point of failure]** Trust API is a single-instance service. If it goes down, commits are blocked. → Mitigation: Fast restart with crash recovery. The ephemeral `/dev/shm` queue survives process restarts (only cleared on VM reboot). Health checks in docker-compose enable auto-restart.

- **[Lock contention under high commit rate]** The `threading.Lock()` serializes all commits. → Mitigation: Lock hold time is minimal (~ms for sysfs write + SQLite INSERT). For expected workloads (container event logging), this is not a bottleneck. If it becomes one, the lock could be sharded per `chain_id` in a future change.

- **[FAILED records block Rekor submission]** A permanently failed record blocks all subsequent submissions for ordering integrity. → Mitigation: Operational alerting on FAILED status. Manual intervention (mark as skipped or delete) can unblock. 10 retries provides substantial tolerance for transient Rekor outages.

- **[prev_log_id not in signature]** Removing `prev_log_id` from the DSSE predicate means a compromised Trust API could reorder entries without detection from the signed envelope alone. → Mitigation: RTMR hardware register is the authoritative ordering proof. The TDX attestation quote binds the RTMR value to the hardware TCB; reordering would require compromising the TDX hardware itself.

- **[REST latency]** Adding a REST hop between tc_api and Trust API increases commit latency. → Mitigation: Both services run on the same host (localhost or Unix socket). Network overhead is negligible compared to Sigstore signing (~seconds).

## Migration Plan

1. **Implement Trust API** as a new FastAPI application with the sequencer lock, expanded schema, embedded submit daemon, and file-lock enforcement.
2. **Refactor tc_api** commit endpoint to perform DSSE signing locally, then POST to Trust API.
3. **Update docker-compose.yml**: Replace `tlog-daemon` service with `trust-api` service. Both tc_api and trust-api share the `/dev/shm` tmpfs mount.
4. **Update start.sh**: Remove `tlog_daemon.py` background launch. Add Trust API startup.
5. **Database migration**: On first Trust API startup, detect old schema (missing `rtmr_extended` column) and run `ALTER TABLE` to add new columns + create `chain_state` table. Existing records get `rtmr_extended=NULL` (treated as unknown → discard on recovery).
6. **Rollback**: Revert to previous `docker-compose.yml` and `start.sh`. Old schema is forward-compatible (new columns have defaults). The standalone daemon can resume from any `PENDING` records.

## Open Questions

- Should Trust API expose a health/readiness endpoint that tc_api checks before accepting commit requests, or should tc_api simply propagate Trust API connection errors to the caller?
- Should `chain_id` be caller-specified or system-generated? Current design assumes it comes from `chain_ref` in the commit request context.
