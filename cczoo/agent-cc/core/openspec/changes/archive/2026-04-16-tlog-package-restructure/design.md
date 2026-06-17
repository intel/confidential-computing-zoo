## Context

After Phase 1A + 1B, the `trusted_container_log/` directory contains 7 files with clean, non-circular dependencies:

```
trusted_container_log/
├── __init__.py          → exports TrustedLogAPI
├── api.py               → TrustedLogAPI (DSSE sign + POST /commit) — used by main.py/services.py
├── database.py          → SQLite queue ops — used only by trucon.py
├── errors.py            → error hierarchy — used by api.py
├── local_mr.py          → LocalMRAdapter ABC + TdxMRAdapter impl — used only by trucon.py
├── tlog_impl.py         → ImmutableLogAdapter ABC + SigstoreLogAdapter impl — used by trucon.py + main.py (lazy)
└── types.py             → Entry, Record, CommitResult etc. — used everywhere
```

Plus `trucon.py` sits at `src/tc_api/trucon.py` as a standalone module containing the FastAPI sequencer app, submit daemon, and crash recovery.

The architecture doc defines adapter interfaces (ABCs) as contracts that could have multiple implementations. The current flat structure mixes contracts with implementations and mixes TruCon internals with tc_api-side code.

## Goals / Non-Goals

**Goals:**
- Separate shared domain contracts (`tlog/`) from TruCon service internals (`trucon/`) from tc_api client code (`tlog_client.py`)
- Make the ABC / implementation boundary explicit in the directory structure
- Prepare for future Phase 3 where `trucon/` could become an independent package
- Keep all existing functionality identical — pure structural refactor

**Non-Goals:**
- Extracting TruCon into an independent pip-installable package (Phase 3)
- Changing any business logic, API signatures, or database schema
- Adding new features or endpoints
- Changing the `sigstore` dependency position (it stays a project-level dep)

## Decisions

### 1. Accept `sigstore.models.Bundle` in the ImmutableLogAdapter ABC

**Decision:** The `ImmutableLogAdapter` ABC keeps `Bundle` in its method signature (`submit_bundle(self, bundle: Bundle, ...)`). The `tlog/` package depends on `sigstore` at the type level.

**Rationale:** The Sigstore Bundle is the core data type of this system's immutable log layer. Abstracting it away (e.g., accepting raw JSON strings) would add serialization overhead at every call site with no meaningful decoupling benefit. Any third-party implementing this ABC would already need to understand Sigstore bundles.

**Alternative considered:** Change ABC signature to `submit_bundle(self, bundle: str, ...)` accepting JSON. Rejected: forces every implementation to deserialize, and the "zero external dependency" goal for `tlog/` isn't worth the ergonomic cost.

### 2. database.py config: parameter injection over relative imports

**Decision:** When `database.py` moves to `trucon/database.py`, change `from ..config import COMMIT_QUEUE_DB` to accept the DB path as a module-level default that can be overridden. The `trucon/app.py` lifespan sets the path from `tc_api.config`.

**Rationale:** This removes the upward import from `trucon/` to `tc_api/config`, making `trucon/` more self-contained for future Phase 3 extraction. The current `DB_PATH` module variable with a fallback default already follows this pattern.

**Alternative considered:** Keep the relative import to `tc_api.config`. Rejected: creates a hard dependency from trucon → tc_api that blocks Phase 3.

### 3. Wrap SigstoreLogAdapter access behind tlog_client

**Decision:** `main.py` currently has a lazy import of `SigstoreLogAdapter` (used in lifespan to create the adapter). After restructure, `tlog_client.py` (formerly `api.py`) exposes a factory or the adapter is injected via `trucon/app.py`. Main.py no longer imports directly from `trucon/adapters/`.

**Rationale:** The tc_api business layer should not reach into TruCon's adapter implementations. The SigstoreLogAdapter is used in `main.py`'s lifespan to construct the `TrustedLogAPI` instance — this wiring can stay in lifespan but import from the correct layer.

**Implementation detail:** `main.py` lifespan imports `SigstoreLogAdapter` from `tc_api.trucon.adapters.sigstore` since it's constructing the full stack. This is acceptable wiring code in the composition root.

### 4. Move order: bottom-up to avoid import breakage

**Decision:** Execute the restructure bottom-up: (1) create new directories + `__init__.py` files, (2) move leaf files first (types, errors), (3) then files with internal deps (ABC files, database), (4) then consumers (app.py, tlog_client.py), (5) update all imports last as a sweep.

**Rationale:** Moving leaf files first means intermediate states are always valid — files that depend on moved files still work because Python import paths are updated incrementally. Moving consumers last avoids circular breakage.

## Risks / Trade-offs

- **[Risk] Import path churn across the codebase** → Every file that imports from `trusted_container_log` needs updating. **Mitigation:** This is a mechanical transformation; grep + replace. The number of unique import patterns is small (~6 distinct import lines).

- **[Risk] pyproject.toml entry point change** → TruCon's uvicorn target changes from `tc_api.trucon:app` to `tc_api.trucon.app:app`. **Mitigation:** Update `start.sh` and `pyproject.toml` in the same commit.

- **[Trade-off] `tlog/` depends on sigstore at type level** → Not truly zero-dependency. Acceptable because sigstore is this system's core.

- **[Trade-off] Intermediate test breakage** → During restructure, imports will be temporarily broken. **Mitigation:** Execute as one atomic change; verify with py_compile after all moves complete.
