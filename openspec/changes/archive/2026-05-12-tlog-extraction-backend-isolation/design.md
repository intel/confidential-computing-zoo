## Context

The current codebase is a single Python package (`tc_api`) that will be merged into `agent-cc/core/` alongside independent sibling projects (`argus`, `tdx-skills`). The trusted-log abstractions — types, ABCs, digest computation — live inside `tc_api.tlog` and are only consumable by importing from `tc_api`. The Sigstore/Rekor backend adapter (`SigstoreLogAdapter`) lives inside `tc_api.trucon.adapters`, coupling the standalone verifier CLI and any future on-chain backend to TruCon sequencer internals.

Current dependency structure:

```
tc_api.tlog/             ← types, ABCs (imports sigstore.models.Bundle in immutable.py)
tc_api.tlog_client       ← TrustedLogAPI (digest functions, DSSE signing, TruCon orchestration)
tc_api.sigstore_baseline ← Event Log 0 baseline bundle (digest functions duplicated)
tc_api.trucon/           ← sequencer, database, adapters/, evidence
tc_api.trucon/adapters/  ← SigstoreLogAdapter, OciBundleMirror, TdxMR, TdxQuote, CCEL
tc_api.cli/verify        ← imports SigstoreLogAdapter directly
docktap/trucon_client    ← imports tc_api.tlog.types.Entry, digest functions
```

Digest computation (`canonical_json`, `compute_entry_digest`, `compute_event_digest`) is duplicated across three files: `tlog_client.py`, `sigstore_baseline.py`, and `trucon/owner_attestation.py`.

## Goals / Non-Goals

**Goals:**

- Extract `tlog` as an independent installable package with zero dependency on `tc_api`
- Extract `tlog-rekor` as a separate backend package isolating Sigstore/Rekor dependencies
- Scaffold `tlog-onchain` for future on-chain backend without pulling Sigstore libraries
- Consolidate duplicated digest computation into a single canonical location in `tlog`
- Enable `cli/verify` to work with only `tlog` + `tlog-rekor` (no TruCon dependency)
- Align directory layout with the `agent-cc/core/` target structure

**Non-Goals:**

- Refactoring `tc-api` internal coupling (trucon↔sigstore_baseline, config monolith) — separate change
- Implementing the on-chain adapter — only scaffold the package
- Abstracting Docker runtime (DockerService → runtime backends) — separate change
- Changing external behavior of any API endpoint or CLI tool
- Migrating tests to new package boundaries (tests update import paths only)

## Decisions

### Decision 1: Remove `sigstore.models.Bundle` from `ImmutableLogAdapter` ABC

**Problem:** `immutable.py` currently `from sigstore.models import Bundle`, making the backend-agnostic ABC depend on a Sigstore-specific type. This would force `tlog` to depend on `sigstore`.

**Choice:** Change `submit_bundle` signature to accept `str` (serialized bundle JSON) instead of `sigstore.models.Bundle`. Each backend adapter deserializes the bundle in its own implementation.

**Rationale:** The submit daemon in `trucon/app.py` already has `bundle_json = payload.get('bundle')` as a string and calls `Bundle.from_json(bundle_json)` before passing to `submit_bundle`. Moving the deserialization into the adapter means the ABC stays type-agnostic while each backend handles its own wire format. An on-chain adapter would never need `sigstore.models.Bundle` at all.

**Alternatives considered:**
- Use `typing.TYPE_CHECKING` guard — still leaks the sigstore import into runtime `isinstance` checks and forces `sigstore` as an install dependency for type checking.
- Use `Any` — loses type safety without gaining clarity. `str` is more descriptive of the actual contract (serialized bundle).

### Decision 2: `tlog` package contents

The standalone `tlog` package contains:

| Module | Contents | Source |
|--------|----------|--------|
| `types.py` | `Entry`, `Record`, `EventLog`, `RecordContext`, `CommitResult`, `CommitQueueStatus`, `LatestState`, `VerificationResult`, `SubmitStatus` | `tc_api/tlog/types.py` (as-is) |
| `errors.py` | `TrustedLogError`, `RecordNotFoundError`, `BackendSubmitError`, `VerificationError` | `tc_api/tlog/errors.py` (as-is) |
| `immutable.py` | `ImmutableLogAdapter` ABC | `tc_api/tlog/immutable.py` (modified: `Bundle` → `str`) |
| `local_mr.py` | `LocalMRAdapter` ABC | `tc_api/tlog/local_mr.py` (as-is) |
| `digest.py` | `canonical_json`, `compute_entry_digest`, `compute_event_digest` | Consolidated from `tlog_client.py`, `sigstore_baseline.py`, `owner_attestation.py` |

**Dependencies:** `hashlib`, `json`, `dataclasses`, `datetime`, `enum`, `typing` — all stdlib. Zero third-party dependencies.

**Not included:** Evidence encoding (`trucon/evidence.py`) stays with TruCon — it's tightly coupled to TDX quote format, `AttestedHeadEvidence` pydantic model, and chain-specific binding computation. Moving it would drag pydantic into `tlog`.

### Decision 3: `tlog-rekor` package contents

| Module | Contents | Source |
|--------|----------|--------|
| `adapter.py` | `SigstoreLogAdapter` | `tc_api/trucon/adapters/sigstore.py` |
| `oci_mirror.py` | `OciBundleMirror` | `tc_api/trucon/adapters/oci_mirror.py` |

**Dependencies:** `tlog`, `sigstore`, `rekor-types`, `cryptography`.

The adapter imports `ImmutableLogAdapter` from `tlog` (not `tc_api.tlog`).

### Decision 4: `tlog-onchain` — scaffold only

Create package structure with `pyproject.toml` depending on `tlog`. Include a stub `adapter.py` with a placeholder class inheriting `ImmutableLogAdapter` that raises `NotImplementedError`. No functional implementation.

### Decision 5: TruCon adapter directory retains platform-specific adapters

After extracting `sigstore.py` and `oci_mirror.py`, `tc_api/trucon/adapters/` retains:
- `tdx_mr.py` — `TdxMRAdapter` implements `LocalMRAdapter` (platform hardware, not immutable log)
- `tdx_quote.py` — TDX quote acquisition
- `ccel.py` — CCEL digest computation

These are TDX hardware abstractions, not immutable-log backends. They stay with TruCon.

### Decision 6: Adapter loading in submit daemon

TruCon's submit daemon currently hardcodes `from tc_api.trucon.adapters.sigstore import SigstoreLogAdapter`. After extraction, it imports from `tlog_rekor.adapter`. The adapter class is selected at init time via environment variable `TC_IMMUTABLE_BACKEND` (default: `rekor`). This is a simple import-time dispatch, not a plugin registry:

```python
def _load_immutable_adapter(backend: str, **kwargs) -> ImmutableLogAdapter:
    if backend == "rekor":
        from tlog_rekor.adapter import SigstoreLogAdapter
        return SigstoreLogAdapter(**kwargs)
    elif backend == "onchain":
        from tlog_onchain.adapter import OnChainLogAdapter
        return OnChainLogAdapter(**kwargs)
    raise ValueError(f"Unknown immutable backend: {backend}")
```

**Rationale:** `entry_points`-based plugin discovery is overkill for 2-3 known backends. Simple conditional import is transparent and debuggable.

### Decision 7: Directory layout aligned with `agent-cc/core/`

Target layout within this repo (before monorepo merge):

```
tlog/
  pyproject.toml
  src/tlog/
    __init__.py
    types.py
    errors.py
    immutable.py
    local_mr.py
    digest.py

tlog-rekor/
  pyproject.toml
  src/tlog_rekor/
    __init__.py
    adapter.py
    oci_mirror.py

tlog-onchain/
  pyproject.toml
  src/tlog_onchain/
    __init__.py
    adapter.py

tc-api/                              (renamed from src/tc_api)
  pyproject.toml                     (updated dependencies)
  src/tc_api/
    ... (existing, with updated imports)
  trucon/adapters/
    tdx_mr.py, tdx_quote.py, ccel.py (sigstore.py and oci_mirror.py removed)
  docktap/                           (moved from top-level)
  config/                            (moved from aa_asr_cdh/)
  tests/
  docs/
```

After monorepo merge, these become `agent-cc/core/tlog/`, `agent-cc/core/tlog-rekor/`, etc.

### Decision 8: Import path migration strategy

Two-phase approach:

**Phase 1 — Compatibility shims:** After moving files, add thin re-export shims at the old import paths:

```python
# src/tc_api/tlog/types.py (shim)
from tlog.types import *  # noqa: F401,F403
```

This prevents a big-bang breakage of all consumers. Tests and application code continue to work immediately.

**Phase 2 — Path update:** Grep-replace all `from tc_api.tlog.` → `from tlog.` and `from tc_api.trucon.adapters.sigstore` → `from tlog_rekor.adapter`. Remove shims. This can be done file-by-file or in one batch.

**Rationale:** Shims let us validate the extraction works before touching every import site. They also allow the monorepo merge to happen without requiring all sibling projects to update simultaneously.

## Risks / Trade-offs

- **[Sigstore version coupling]** `tlog-rekor` pins Sigstore library versions independently from `tc-api`. If both are installed editable in the same venv, version conflicts are possible. → Mitigation: Use compatible version ranges; CI tests with combined install.

- **[Bundle serialization overhead]** Changing `submit_bundle(Bundle)` to `submit_bundle(str)` adds a `Bundle.from_json()` call inside the adapter. → Mitigation: Negligible compared to network I/O for Rekor submission. The submit daemon already holds the JSON string form.

- **[Shim maintenance]** Compatibility shims at old import paths add temporary indirection. → Mitigation: Phase 2 removes them. Shims are thin re-exports, not logic. Lint with `# noqa` annotations.

- **[Test import churn]** ~20 test files import from `tc_api.tlog.*` or `SigstoreLogAdapter`. → Mitigation: Shims make this non-blocking; batch update in Phase 2.

- **[Circular dependency risk during extraction]** `tlog_client.py` imports from `tlog` (types) but also calls digest functions that will move to `tlog.digest`. After extraction, `tlog_client.py` imports from both `tlog` and `tc_api` internals — this is the intended dependency direction (tc_api → tlog). → No mitigation needed; this is correct.

## Open Questions

- **Evidence encoding location:** `trucon/evidence.py` contains `AttestedHeadEvidence` and binding computation. Should any of this move to `tlog` in a future iteration, or is it permanently TruCon-specific? Current decision: stays with TruCon.

- **Package name `tlog` conflicts:** The PyPI name `tlog` may already be taken. For internal/monorepo use this doesn't matter, but if ever published externally, a scoped name (`tc-tlog` or `trustlog`) may be needed.

- **Digest function ownership in `sigstore_baseline.py`:** After consolidation into `tlog.digest`, the private duplicates in `sigstore_baseline.py` and `owner_attestation.py` should import from `tlog.digest`. This is a code cleanup step, not a structural decision.
