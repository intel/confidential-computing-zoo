## Context

The architecture (trusted-log/architecture.md §Digest Algorithm) specifies a two-level digest:

```
Entry_Digest_i = SHA384(Canonical({key_i, value_i}))
Event_Digest   = SHA384(Canonical({event_id, event_type, created, [Entry_Digest_1, ..., Entry_Digest_n]}))
```

Currently, `tlog_client.py:commit_record()` performs a single-level hash — raw entries are embedded in the predicate and a single SHA-384 pass covers the entire payload. The change is localized to the digest producer (`tlog_client.py`); the TruCon server receives and stores the final `event_digest` string without recomputing it.

## Goals / Non-Goals

**Goals:**
- Implement the architecture-specified two-level digest algorithm.
- Expose `compute_entry_digest()` and `compute_event_digest()` as testable module-level functions.
- Predicate includes both raw `entries` (auditing) and `entry_digests` (verification).

**Non-Goals:**
- Backward compatibility with old digest values — no production data exists.
- Changes to TruCon server (`trucon/app.py`, `trucon/database.py`) — it is a digest consumer, not producer.
- Digest versioning or migration logic.

## Decisions

### 1. Predicate includes both raw entries and entry digests

**Decision**: The DSSE predicate payload contains `entries` (raw key/value list for human auditing) and `entry_digests` (SHA-384 hex strings for cryptographic verification). The `digest` field (event digest) is computed only from `{event_id, event_type, created, entry_digests}` — raw entries do not influence the digest.

**Alternatives considered**:
- (A) Only entry_digests in predicate — rejects auditing without external lookup.
- (C) Only raw entries, change algorithm silently — entry_digests not explicit, harder to verify independently.

**Rationale**: Option B gives both auditability and independent entry-level integrity verification in one signed bundle.

### 2. Helper functions as module-level in tlog_client.py

**Decision**: Two new functions at module scope in `tlog_client.py`:
- `compute_entry_digest(key: str, value: str) -> str` — returns `"sha384:<hex>"`
- `compute_event_digest(event_id: str, event_type: str, created_iso: str, entry_digests: list[str]) -> str` — returns `"sha384:<hex>"`

Both use existing `canonical_json()` for deterministic serialization.

**Alternatives considered**:
- New module `src/tc_api/tlog/digest.py` — cleaner separation but adds a file for 20 lines.
- Inline in `commit_record()` — not independently testable.

**Rationale**: Module-level functions keep the change minimal, avoid new files, and allow direct unit testing via import.

### 3. No backward compatibility

**Decision**: New digest algorithm replaces old one. No digest version field, no dual-mode verification.

**Rationale**: This is development-phase. No production chain data exists. The `/verify-chain` endpoint compares stored `event_digest` against RTMR chain (`SHA384(prev_mr + event_digest)`) — it never recomputes event_digest from entries, so old DB rows remain verifiable.

## Risks / Trade-offs

- **[Predicate size increase]** → Adding `entry_digests` array alongside `entries` increases DSSE bundle size by ~100 bytes per entry. Acceptable — entries are typically < 10 per event.
- **[canonical_json sort_keys interaction]** → `compute_entry_digest` hashes `{"key": k, "value": v}`. With `sort_keys=True` this is deterministic regardless of dict construction order. No risk.
- **[Test mock digests]** → Existing tests use fake digest strings (`"sha384:" + "ab"*48`). They will not break because they never call the real digest functions. New tests will cover the real computation.
