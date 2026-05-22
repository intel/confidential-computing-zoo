## Context

Docktap is a Unix socket proxy that intercepts Docker API traffic between the CLI and the daemon. It captures operation metadata (pull, create, start, stop, rm) and logs structured JSON. Currently it has zero integration with TruCon — the trust event sequencer that serializes RTMR extends, manages the commit queue, and publishes to immutable backends.

The existing tc_api → TruCon integration path (in `tlog_client.py`) performs DSSE signing with Sigstore using ambient OIDC credentials, then POSTs signed bundles to TruCon's `/commit` endpoint. Docktap needs to replicate this commit path.

Key existing code:
- `docktap/proxy/docker_proxy.py`: `handle_client()` streams the Docker response back to CLI first, then enriches the `OperationRecord` and logs it. The TruCon commit hook goes after response streaming.
- `src/tc_api/tlog_client.py`: `TrustedLogAPI` handles record init → entry append → DSSE signing → POST /commit. The signing logic (entry digest, event digest, DSSE statement, Sigstore signing) is what Docktap needs.
- `docktap/proxy/operation_log.py`: `OperationRecord` dataclass contains all captured Docker operation metadata.

## Goals / Non-Goals

**Goals:**
- Docktap submits signed DSSE bundles to TruCon for `pull`, `create`, `start`, `stop`, `rm` operations.
- Submission happens after the Docker response is returned to CLI (no added latency on the Docker API path).
- TruCon failures are best-effort — logged as warnings, never blocking Docker operations.
- Events from Docktap and REST workers share the same `sequence_num` ordering on the default chain.

**Non-Goals:**
- Per-workload chain assignment (deferred to GAP-11).
- Rich Entry types (deferred to FIX-04). Uses flat `Entry(key, value)`.
- Local event buffering or async queue inside Docktap.
- OIDC token caching or refresh optimization.
- Submitting non-lifecycle operations (wait, rmi, inspect, preflight, unknown).

## Decisions

### 1. Shared signing code via direct import

**Decision**: Docktap imports digest utilities from `tlog.digest` and uses tc_api trust/identity helpers plus `sigstore` directly for DSSE construction and signing.

**Alternatives considered**:
- *Copy the signing code into Docktap*: Leads to drift between two signing implementations. Rejected.
- *Create a shared `tc_common` package*: Over-engineering for this stage. Can refactor later if needed.
- *Have Docktap call tc_api which calls TruCon*: Extra hop, adds coupling to tc_api availability. Rejected.

**Rationale**: The `tc_api` package is already installed in the project (`pip install -e .`). Docktap can import from it. The signing functions are pure computations with no side effects.

### 2. Commit client as a new module in Docktap

**Decision**: Create `docktap/trucon_client.py` — a lightweight commit client that:
1. Takes an `OperationRecord` + operation type.
2. Constructs `Entry(key, value)` pairs from the record's metadata.
3. Computes entry digests and event digest using imported functions.
4. Builds the DSSE statement and signs with Sigstore.
5. POSTs to TruCon `/commit` with `chain_id="default"`.
6. Returns success/failure (caller decides what to do on failure).

**Rationale**: Keeps Docktap's proxy code clean. The commit logic is isolated and testable. The `handle_client` method just calls `try: submit_to_trucon(op_record) except: log warning`.

### 3. Integration point: after response streaming, before client close

**Decision**: The TruCon commit call is placed after `enrich_from_response()` and `log_operation_json()` in `handle_client()`, but before the `finally: client_socket.close()` block. At this point the Docker response has already been fully streamed back to the CLI.

```
Docker CLI ──▶ Docktap proxy ──▶ Docker Daemon
                    │◀── response streamed back to CLI ──│
                    │
                    ├── enrich_from_response(op_record)
                    ├── tracker.add(op_record)
                    ├── log_operation_json(op_record)
                    ├── [NEW] submit_to_trucon(op_record)  ← best-effort
                    │
                    └── client_socket.close()
```

**Rationale**: The client already has its Docker response. The commit is a fire-and-forget addition. If it fails, the Docker operation succeeded — we just log the trust submission failure.

### 4. Entry mapping from OperationRecord

**Decision**: Each operation type maps to a fixed set of `Entry(key, value)` pairs:

| Operation | Entries |
|-----------|---------|
| `pull` | `("operation_type", "pull")`, `("image_name", ...)`, `("image_tag", ...)`, `("image_digest", ...)` |
| `create` | `("operation_type", "create")`, `("image_name", ...)`, `("container_name", ...)`, `("container_id", ...)` |
| `start` | `("operation_type", "start")`, `("container_id", ...)` |
| `stop` | `("operation_type", "stop")`, `("container_id", ...)` |
| `rm` | `("operation_type", "rm")`, `("container_id", ...)` |

All values are JSON-encoded strings (consistent with tc_api's existing convention). Missing fields are omitted rather than set to null.

### 5. OIDC token acquisition

**Decision**: Use `sigstore.oidc.detect_credential()` on each commit call (same as tc_api). No caching.

**Rationale**: Simplicity. OIDC tokens are short-lived. Docktap operations are infrequent enough (Docker operations per second is low) that the per-call overhead is acceptable. Caching can be added later if profiling shows a bottleneck.

### 6. Filtering: only lifecycle operations

**Decision**: A set `SUBMITTABLE_OPERATIONS = {"pull", "create", "start", "stop", "rm"}` gates which operations trigger a TruCon commit. The check happens early to avoid unnecessary signing work.

## Risks / Trade-offs

- **[Sigstore availability]** → If the OIDC credential source is unavailable, every commit fails silently. Mitigation: best-effort + warning logging. Operators monitor for sustained warning patterns.
- **[TruCon availability]** → If TruCon is down, Docker operations continue but trust events are lost. Mitigation: This is the accepted v1 trade-off. Local buffering deferred to a future enhancement.
- **[Import coupling]** → Docktap imports from `tlog.digest` and tc_api trust/identity helpers. If those APIs change, Docktap breaks. Mitigation: The imported digest functions (`compute_entry_digest`, `compute_event_digest`, `canonical_json`) are stable utility functions. Pin to specific function signatures, not internal classes.
- **[Thread-per-connection + synchronous HTTP]** → Each Docker operation's handler thread blocks on the TruCon HTTP call. With thread-per-connection model this is fine for typical Docker workloads. High-concurrency scenarios could exhaust threads. Mitigation: TruCon calls have a short timeout (5s). Acceptable for v1 — async can be considered if thread exhaustion is observed.
- **[Lost events on crash]** → If Docktap crashes between Docker response and TruCon commit, the event is lost. Mitigation: Acceptable for v1 — the Docker response was already returned successfully. Crash recovery is out of scope.
