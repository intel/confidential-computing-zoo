## Context

TruCon's `verify-chain` endpoint currently performs three checks: sequence continuity, RTMR chain integrity (SHA384 hash chain), and Rekor confirmation status. When TDX hardware is absent, `mr_value` is NULL for all records, so the RTMR check is skipped entirely (`mr_ok: null`). This leaves only `sequence_num` gap detection as an ordering check — insufficient for testing the verification flow.

The `prev_log_id` column already exists in `commit_queue` and is populated on every commit (read from `chain_state.head_log_id`). The `log_id` column is set when a record is confirmed by the immutable backend. These two columns already form a linked-list structure in the database:

```
record[0].log_id = "rekor-abc"     record[0].prev_log_id = null
record[1].log_id = "rekor-def"     record[1].prev_log_id = "rekor-abc"  ← matches record[0].log_id
record[2].log_id = null (pending)  record[2].prev_log_id = "rekor-def"  ← matches record[1].log_id
```

The linkage breaks at the unconfirmed tail because `log_id` is only assigned on confirmation and `prev_log_id` for subsequent records comes from `chain_state.head_log_id` (which also only updates on confirmation).

## Goals / Non-Goals

**Goals:**
- Provide a DB-level `prev_log_id` chain verification in `verify-chain` when RTMR is unavailable
- Make non-TEE mode clearly visible at startup via a prominent warning
- Enable meaningful verification testing on non-TDX development machines

**Non-Goals:**
- Cryptographic ordering proof in non-TEE mode (no changes to DSSE predicate or signing flow)
- Explicit env var to force non-TEE mode (`TRUCON_FORCE_NO_TEE`) — auto-detection via TDX sysfs is sufficient
- Adding a new `ordering_proof` field to the response model — existing `rtmr_available: bool` is sufficient

## Decisions

### D1: prev_log_id verification as fallback, not replacement

When `rtmr_available == False`, `verify-chain` adds a `prev_log_id` linkage check for each record. When `rtmr_available == True`, the check is skipped (RTMR chain is the authoritative proof). This keeps the two modes cleanly separated.

**Rationale**: The prev_log_id check is DB-level consistency, not cryptographic proof. Mixing it with RTMR verification would be confusing — if RTMR passes, prev_log_id is redundant.

### D2: Unconfirmed tail accepted as unverifiable

Records without `log_id` (not yet confirmed) cannot participate in `prev_log_id` verification because: (a) they have no `log_id` for the next record to link to, and (b) their `prev_log_id` may still be valid if the previous record is confirmed. The check reports `prev_log_id_ok: null` for records where verification is not possible.

**Rationale**: This matches the existing behavior where `mr_ok: null` is reported when RTMR values are missing. Unconfirmed records are already tracked via `rekor_pending`.

### D3: Per-entry `prev_log_id_ok` field

Each entry in the verification response gains a `prev_log_id_ok: bool | null` field with semantics:
- `true`: record's `prev_log_id` matches previous record's `log_id` (or is `null` for first record)
- `false`: mismatch detected (ordering violation)
- `null`: cannot verify (RTMR mode active, or record/predecessor not confirmed)

**Rationale**: Follows the same pattern as `mr_ok` — a tri-state that distinguishes "verified OK", "verified FAIL", and "cannot verify".

### D4: Startup warning upgrade

Change the "TDX RTMR sysfs not found" message from `logger.info()` to `logger.warning()` with explicit "NON-TEE MODE" banner text indicating this is for development/testing only.

## Risks / Trade-offs

- **[DB-level only]** → `prev_log_id` chain is not signed, so a compromised database could forge linkage. Mitigated: this mode is explicitly test-only; production uses TDX RTMR.
- **[Unverifiable tail]** → Chain tail always shows `prev_log_id_ok: null`. Mitigated: mock-confirmation (no-backend path) in dev immediately sets `log_id`, so dev testing typically has full coverage.
