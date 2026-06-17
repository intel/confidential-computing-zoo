## Context

The project has two branches that evolved in parallel:
- **Upstream** (`4d03d90`): Created a top-level `architecture.md` with a 3-service TruCon vision (REST + Docktap + TruCon), introduced an `introduce-trucon-event-orchestrator` openspec change (0/15 tasks), deleted several `trusted_container_log/` files, and made minor wording changes to `trusted-log/` docs. The trusted-log module docs still describe the pre-refactor monolithic model.
- **Our branch** (HEAD): Implemented the `tlog-sequencer-refactor` (37/37 tasks), creating a working split architecture with `trust_api.py`, expanded SQLite schema, crash recovery, embedded submit daemon, and updated all `trusted-log/` docs to match the implementation.

The merge (commit `565cb46`) brought upstream's files into our branch. Our modified files were kept over upstream's deletions. The result: working code uses "Trust API" naming while upstream's vision uses "TruCon". The two-tier doc structure needs formalization.

Stakeholders: upstream maintainer (edmund), local development, future consumers of trusted-log as an independent module.

## Goals / Non-Goals

**Goals:**
- Unify naming to "TruCon" across all code, config, and docs.
- Formalize two-tier documentation: top-level `architecture.md` (system vision) and `trusted-log/` (self-contained implementation detail).
- Update top-level `architecture.md` to reflect implemented reality while preserving Docktap and instance mapping as planned.
- Document prev_log_id chaining as a future secondary ordering method.
- Ensure all existing tests pass after rename.

**Non-Goals:**
- Implementing Docktap integration, instance mapping, or idempotency.
- Changing any runtime behavior or external API.
- Expanding lifecycle states beyond current 3 (PENDING, CONFIRMED, FAILED).
- Adding prev_log_id to the DSSE predicate (future work).
- Modifying upstream's `introduce-trucon-event-orchestrator` change or its tasks.

## Decisions

### 1. Filename: `trust_api.py` → `trucon.py`
- **Choice:** Single file rename to `trucon.py`, uvicorn target becomes `trucon:app`.
- **Rationale:** Matches upstream's canonical name. Short, unambiguous.
- **Alternative considered:** `trucon_api.py` or `trucon_service.py`. Rejected — `trucon.py` is sufficient since it's the sole module, and the `.py` extension already implies it's code.

### 2. Config: `TRUST_API_URL` → `TRUCON_URL`
- **Choice:** Rename envvar and all references. Default stays `http://127.0.0.1:8001`.
- **Rationale:** Aligns with service name.

### 3. Two-tier doc boundary: one-way dependency
- **Choice:** `trusted-log/` docs are self-contained with zero references to top-level `architecture.md`. Top-level `architecture.md` references `trusted-log/` docs for implementation detail.
- **Rationale:** The trusted-log module may be extracted as an independent project. Self-containment ensures the docs remain valid after extraction.
- **Alternative considered:** Bidirectional references. Rejected — creates coupling that breaks on extraction.

### 4. Top-level `architecture.md` content strategy
- **Choice:** Update upstream's top-level `architecture.md` to reflect our implemented TruCon architecture (sequencer lock, embedded daemon, SQLite queue, crash recovery) as the current state. Retain Docktap Service and instance mapping sections but mark them as "Planned". Remove details that belong in `trusted-log/architecture.md` (threading.Lock internals, SQLite schema columns, crash recovery flags).
- **Rationale:** Top-level doc should describe system topology and inter-service contracts, not module internals. Avoids duplication with `trusted-log/architecture.md`.

### 5. prev_log_id: document-level optionality
- **Choice:** Add a section in `trusted-log/architecture.md` describing prev_log_id chaining as a future secondary ordering method. Current default (RTMR-based ordering, prev_log_id not in DSSE predicate, system-maintained in SQLite) stays unchanged. No config flag or code change.
- **Rationale:** Defers complexity. The RTMR ordering model is proven and implemented. prev_log_id signing is useful for non-TEE environments but requires verification model changes. Document the intent now, implement later.
- **Alternative considered:** Add a config flag now. Rejected — scope creep, no immediate consumer.

### 6. Docktap in top-level doc
- **Choice:** Preserve upstream's Docktap Service section in top-level `architecture.md` with "Planned" status annotations. Do not add Docktap references to `trusted-log/` docs.
- **Rationale:** Docktap is a legitimate future integration point. Documenting it in the top-level vision doc costs nothing and provides context for future work.

### 7. Existing files: keep all
- **Choice:** Keep all files that upstream deleted but we still use (`trusted_container_log/api.py`, `database.py`, `errors.py`, `types.py`, `local_mr.py`, `tlog_impl.py`, tests). These survived the merge because git prefers "modify" over "delete".
- **Rationale:** All files are actively imported by production code and tests.

## Risks / Trade-offs

- [Risk] Rename may break imports in developer environments with cached `.pyc` files.
  → Mitigation: Test clean import after rename. Document in commit message to `find . -name '*.pyc' -delete`.

- [Risk] Upstream's `introduce-trucon-event-orchestrator` change has 15 unstarted tasks that reference a different architecture than what we implement.
  → Mitigation: Out of scope for this change. That change can be updated separately after the merge.

- [Risk] Two-tier docs may drift if one is updated without the other.
  → Mitigation: Top-level doc references `trusted-log/` for detail. Cross-reference makes drift visible during review.

- [Trade-off] Marking Docktap and instance mapping as "Planned" may mislead readers into thinking implementation is imminent.
  → Mitigation: Use explicit "Status: Planned — not yet implemented" labels.

## Open Questions

- None. All questions resolved during explore session.
