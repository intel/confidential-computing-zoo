## Context

Docktap intercepts Docker CLI operations via a Unix socket proxy and submits signed DSSE bundles to TruCon's `POST /commit` endpoint. Currently all events use a hardcoded `chain_id="default"`, merging unrelated workloads into one trust chain.

TruCon already supports arbitrary `chain_id` values — `chain_state`, `commit_queue`, and `sequence_num` are all partitioned per chain. The gap is entirely on the Docktap side: extracting a workload identifier and routing events to the correct chain.

The `OperationTracker` in `docktap/proxy/operation_log.py` maintains in-memory maps for `container_id → OperationRecord`, but these are lost on Docktap restart. Only `docker create` carries the full container configuration (including labels); subsequent operations (`start`, `stop`, `rm`) reference containers by ID only.

## Goals / Non-Goals

**Goals:**
- Docktap resolves `chain_id` from a Docker container label (`io.trucon.workload-id`) at create time.
- Subsequent operations for the same container route to the resolved chain.
- The container → workload mapping survives Docktap process restarts via SQLite persistence.
- Containers without the label fall back to `chain_id="default"`.

**Non-Goals:**
- TruCon changes (it already handles arbitrary chain_ids).
- Workload/instance mapping model or query endpoints (GAP-03 — separate change).
- Per-workload audit or verification tooling.
- Label validation beyond presence check (format constraints deferred).
- Migration of historical events from `"default"` chain to per-workload chains.

## Decisions

### D1: Label convention — `io.trucon.workload-id`

Use the OCI reverse-domain-name convention for the label key.

**Rationale:** `tc.workload_id` (considered earlier) lacks namespace protection and uses underscore instead of the Docker-conventional hyphen. `io.trucon.workload-id` follows the same pattern as `io.containerd.*`, `org.opencontainers.*`, and avoids collision with user labels.

**Alternative:** A `--env` variable or TruCon-side config mapping. Rejected because labels are the Docker-native metadata mechanism, travel with the container config, and are visible in `docker inspect`.

### D2: Separate Docktap SQLite for container mapping

Introduce a new `docktap/workload_store.py` module with its own SQLite database (`/dev/shm/docktap/container_map.db`), rather than extending TruCon's database or the OperationTracker's in-memory storage.

**Rationale:**
- Docktap and TruCon run as separate processes; sharing a SQLite file introduces cross-process locking complexity.
- The mapping table is trivially small (`container_id`, `workload_id`, `created_at`) — no schema debt.
- `/dev/shm/` placement matches TruCon's ephemeral storage strategy and avoids writing secrets to persistent disk in confidential computing environments.
- Host reboot clears tmpfs, but also destroys all containers, so no orphaned mappings.

**Alternative:** Persist in OperationTracker memory only. Rejected because Docktap restart loses all mappings, causing `stop`/`rm` events to mis-route to `"default"` chain.

### D3: Write on create, read on subsequent ops

Only `docker create` writes to the mapping store. `start`/`stop`/`rm` read the mapping to resolve `chain_id`. If no mapping is found (container created before Docktap started, or Docktap + host both restarted), fall back to `"default"`.

**Rationale:** `docker create` is the only operation that carries the full container config (labels). This is the minimal write surface. The fallback preserves forward compatibility and doesn't break existing behavior.

### D4: chain_id = workload_id value (direct passthrough)

The label value is used directly as `chain_id` with no transformation.

**Rationale:** TruCon already accepts arbitrary strings as `chain_id` and creates chain state on first use. Adding a mapping layer (e.g., hashing, prefixing) adds complexity without benefit. If format constraints are needed later, they can be added at the label validation stage.

### D5: Multiple containers per workload share one chain

All containers with the same `io.trucon.workload-id` label submit events to the same chain. Events from different containers interleave in commit-arrival order.

**Rationale:**
- Provides workload-level tamper-evident ordering via RTMR hash chain — a verifier can prove the exact sequence of all lifecycle events within a workload.
- Container lifecycle event frequency is low (seconds between operations); TruCon's `_sequencer_lock` hold time is sub-millisecond, so serialization is not a bottleneck.
- Per-container chains would lose cross-container ordering proof and complicate audit (verifier must correlate multiple chains without a shared ordering anchor).

## Risks / Trade-offs

- **[tmpfs loss on host reboot]** → Acceptable: host reboot also destroys all containers. No orphaned mappings possible.
- **[Docktap restart without host reboot]** → tmpfs file persists; mapping survives. Covered by design.
- **[Label value collisions across users/tenants]** → Out of scope for GAP-11. If multi-tenant isolation is needed, a namespace prefix convention or TruCon-side admission policy can be added later.
- **[Large number of distinct workload_ids]** → Each unique chain_id creates one row in `chain_state`. SQLite handles millions of rows; not a practical concern.
- **[Container created outside Docktap's proxy]** → Mapping won't exist; events fall back to `"default"`. This is expected behavior for externally-managed containers.
