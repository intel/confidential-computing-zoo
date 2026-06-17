## Context

Phase 1A (completed, archived as `2026-04-16-migrate-tlog-to-trucon-phase1a`) migrated all business endpoints (build, publish, launch, lunks) from `ChainedTransparencyLog` to `TrustedLogAPI → TruCon`. The legacy code was intentionally left in place during 1A:

- `tlog_chain.py` — ~400 lines of legacy chain management, Sigstore signing, local file persistence
- `verify_tlog()` in `services.py` (~line 1740) — uses a local import of `ChainedTransparencyLog` for file-based chain verification
- `/api/verify-tlog` endpoint in `main.py` — accepts uploaded `.sigstore.json` files, calls `verify_tlog()`
- `__init__.py` exports `ChainedTransparencyLog` as the module's public API

This is a POC project with no deployed systems. There are no backward compatibility constraints. Legacy file formats (`.sigstore.json` chain backups) can be abandoned.

TruCon currently stores commit data in SQLite (`commit_queue` + `chain_state` tables) and performs RTMR extends, but has no way to verify the chain's integrity beyond a lightweight `GET /chain-state/{chain_id}` head-check. The `event_digest` used for RTMR extend is not persisted, making chain replay verification impossible without parsing DSSE bundles.

## Goals / Non-Goals

**Goals:**
- Delete all `ChainedTransparencyLog` code and references from the codebase
- Remove the `/api/verify-tlog` endpoint and `verify_tlog()` service method
- Add `event_digest` persistence to TruCon's `commit_queue` table
- Add `GET /verify-chain/{chain_id}` endpoint to TruCon with full chain traversal: sequence continuity, RTMR chain integrity, and Rekor confirmation status — returning detailed per-entry results

**Non-Goals:**
- Restructuring the `trusted_container_log/` directory layout (Phase 2)
- Namespace separation of TruCon into its own package (Phase 3)
- Modifying `TrustedLogAPI.verify_record()` (Rekor-level verification, unchanged)
- Adding a tc_api proxy endpoint for TruCon verify-chain (can be added later if needed)

## Decisions

### 1. Persist `event_digest` in `commit_queue` table

**Decision:** Add an `event_digest TEXT` column to the `commit_queue` table. The `/commit` endpoint stores `req.event_digest` alongside the existing fields.

**Rationale:** RTMR chain verification requires replaying `mr[i] = SHA384(mr[i-1] || digest[i])` for each entry. Currently `event_digest` is consumed by `_local_mr.extend()` and discarded. Without it, verification would need to extract the digest from the DSSE bundle payload — fragile and couples verification to the signing format.

**Alternative considered:** Extract digest from `payload.bundle` at verification time. Rejected because it couples the verification logic to DSSE bundle internals and breaks if the bundle format changes.

**Migration:** Add column with `ALTER TABLE commit_queue ADD COLUMN event_digest TEXT`. Existing rows will have `NULL` — the verification endpoint treats `NULL` as "RTMR check skipped for this entry" rather than a failure.

### 2. Verification response: detailed per-entry results (Option B)

**Decision:** `GET /verify-chain/{chain_id}` returns a JSON response with a top-level summary and a per-entry `entries` array. Each entry includes `seq`, `record_id`, `event_id`, `mr_ok`, `rekor_ok`, `rtmr_extended`, `mr_value`, and an optional `error` string.

**Rationale:** Detailed per-entry output is essential for debugging chain integrity issues in a TEE environment where state is opaque. A boolean-only response hides the location and nature of failures.

**Response format:**
```json
{
  "valid": true,
  "chain_id": "default",
  "total_entries": 42,
  "mr_verified": 42,
  "rekor_confirmed": 40,
  "rekor_pending": 2,
  "rtmr_available": true,
  "head_mr_value": "0xabcd...",
  "first_error_at": null,
  "entries": [
    {
      "seq": 1,
      "record_id": "uuid",
      "event_id": "evt-xxx",
      "mr_ok": true,
      "rekor_ok": true,
      "rtmr_extended": true,
      "mr_value": "0x1234..."
    }
  ]
}
```

### 3. RTMR-unavailable environments: skip instead of fail

**Decision:** If all `mr_value` entries in the chain are `NULL` (non-TDX environment), the verification endpoint sets `rtmr_available: false` and skips RTMR checks. All entries get `mr_ok: null` rather than `false`. The chain is verified only on sequence continuity and Rekor status.

**Rationale:** TruCon runs in development environments without TDX hardware. Failing verification on missing RTMR would make the endpoint unusable outside production TEEs.

### 4. Verification algorithm

**Decision:** The endpoint queries all `commit_queue` records for the given `chain_id`, ordered by `sequence_num`, and checks three properties per entry:

1. **Sequence continuity:** `entry.sequence_num == expected_seq` (starting at 1, incrementing by 1). Gap or duplicate → error.
2. **RTMR chain integrity** (if `event_digest` present): `SHA384(prev_mr || entry.event_digest) == entry.mr_value`. First entry uses all-zeros as `prev_mr`.
3. **Rekor confirmation:** `entry.status == "CONFIRMED"` and `entry.log_id IS NOT NULL`.

The first error sets `first_error_at` and `valid: false`, but traversal continues to report all errors.

### 5. Clean deletion of legacy code

**Decision:** Delete `tlog_chain.py` entirely, remove the `/api/verify-tlog` endpoint from `main.py`, remove `verify_tlog()` from `services.py`, and change `__init__.py` to export `TrustedLogAPI` instead of `ChainedTransparencyLog`.

**Rationale:** No deployed systems, no compatibility constraints, no tests reference the legacy code. Clean removal simplifies the codebase.

## Risks / Trade-offs

- **[Risk] Existing `commit_queue` rows lack `event_digest`** → RTMR verification will be partial for pre-migration records. **Mitigation:** Verification treats `NULL event_digest` as "skipped" per entry, does not mark the chain as invalid for missing historical data.

- **[Risk] Large chains may be slow to verify** → Full table scan of `commit_queue` for a chain. **Mitigation:** Add index on `(chain_id, sequence_num)` if not already present. For this POC stage, chains are small (dozens of entries).

- **[Trade-off] No tc_api proxy endpoint for verify-chain** → Clients must call TruCon directly at port 8001. Acceptable for POC; can add a proxy endpoint later if needed.

- **[Trade-off] `__init__.py` export change is breaking** → Any external code importing `from tc_api.trusted_container_log import ChainedTransparencyLog` will break. Acceptable: this is POC with no external consumers.
