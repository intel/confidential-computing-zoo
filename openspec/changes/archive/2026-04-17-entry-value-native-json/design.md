## Context

`Entry` is the atomic evidence unit in the trusted log. Every build, publish, launch, and Docktap operation records facts as `Entry` objects that are hashed into a two-level digest chain, signed into DSSE envelopes, extended into RTMR[2], and submitted to Rekor.

Current state:
- `Entry(key: str, value: str)` — all values are pre-serialized via `json.dumps()`.
- DSSE predicate contains double-encoded JSON: `{"key": "config", "value": "{\"config_dir\":\"/path\"}"}`.
- Docktap uses raw `(key, value)` tuples instead of `Entry`, with its own predicate construction.
- `compute_entry_digest()` hashes `canonical_json({"key": k, "value": v})` where `v` is already a string.
- No production data exists — format can change without migration.

## Goals / Non-Goals

**Goals:**
- `Entry.value` accepts any JSON-compatible type (`str | dict | list | int | float | bool | None`).
- Eliminate `json.dumps()` wrapping at all call sites.
- DSSE predicate contains native JSON values (single encoding layer).
- Docktap uses `Entry` objects imported from `tc_api.tlog.types`.
- Two-level digest computation works correctly with native values via `canonical_json()`.
- Fix `"verfiy_sbom_status"` typo → `"verify_sbom_status"`.

**Non-Goals:**
- Schema validation on entry keys or value shapes (future work).
- Typed/structured `Entry` subclasses per event type (rejected as over-coupled; see FIX-04 analysis).
- Changes to the digest algorithm itself (SHA-384, two-level structure unchanged).
- Changes to DSSE envelope structure, signing flow, or Rekor submission.

## Decisions

### D1: `Entry.value` type — `Any` with runtime JSON-compatibility constraint

`value: Any` in the dataclass. The only constraint is that the value must be JSON-serializable (enforced implicitly by `canonical_json()` which calls `json.dumps()`). No runtime type check added — if a caller passes a non-serializable value, `canonical_json()` raises `TypeError` at commit time, which is the correct failure point.

**Alternative considered**: `value: Union[str, dict, list, int, float, bool, None]` — rejected because Python's type union doesn't add runtime safety and is verbose without benefit. The implicit `json.dumps()` serialization is the real contract.

### D2: Digest computation — no algorithm change

`compute_entry_digest(key, value)` changes its signature from `(str, str)` to `(str, Any)`. Internally it still calls `canonical_json({"key": key, "value": value})` → `SHA384()`. Since `canonical_json()` uses `json.dumps(sort_keys=True, separators=(',', ':'))`, nested dicts/lists are deterministically serialized. The digest for the same logical data is **different** from the old format (because the old format double-encoded values), but this is acceptable since no production data exists.

### D3: Docktap imports `Entry` from `tc_api.tlog.types`

Docktap already runs in the same CVM where tc_api is installed in editable mode. Direct import is the simplest path. `_build_entries()` returns `List[Entry]` instead of `List[Tuple[str, str]]`, and `_build_commit_payload()` serializes entries via `{"key": e.key, "value": e.value}` (same as tc_api's predicate construction).

**Alternative considered**: shared types package — rejected as unnecessary indirection for a single-CVM deployment.

### D4: Typo fix is bundled

`"verfiy_sbom_status"` → `"verify_sbom_status"` is fixed as part of this change since we're touching all `Entry` call sites anyway. No compatibility concern.

## Risks / Trade-offs

- **[Risk] Callers pass non-JSON-serializable objects** → `canonical_json()` raises `TypeError` at commit time. This is a clear, early failure at the system boundary. No additional validation needed.
- **[Risk] Existing tests hardcode digest values** → Tests must be updated to expect new digest outputs (native value encoding ≠ double-encoded string). Identified test files: `test_two_level_digest.py`, `test_unit.py`, Docktap tests.
- **[Trade-off] `value: Any` loses static type checking** → Accepted. The real contract is JSON-serializability, which is a runtime property. Type narrowing would be cosmetic.
