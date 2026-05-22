## Why

`Entry(key: str, value: str)` forces all callers to `json.dumps()` structured data into strings, producing JSON-in-JSON double encoding in DSSE predicates. Audit tools must double-parse every value, the wire format is harder to read, and there is no path to schema validation. Eliminating this encoding layer improves clarity, reduces serialization bugs, and unblocks future extensibility (e.g., entry-level schema enforcement).

## What Changes

- **BREAKING**: `Entry.value` type changes from `str` to `Any` (JSON-compatible: `str | dict | list | int | float | bool | None`).
- All `add_entry()` call sites in `main.py`, `services.py`, and `docktap/trucon_client.py` stop wrapping values in `json.dumps()`.
- `compute_entry_digest()` accepts native JSON objects; `canonical_json()` already handles nested structures deterministically.
- DSSE predicate `entries[i].value` becomes a native JSON value instead of an escaped JSON string.
- Docktap switches from `(key, value)` tuples to importing and using `Entry` objects from `tc_api.tlog.types`.
- Fix existing typo: `"verfiy_sbom_status"` → `"verify_sbom_status"` across all call sites.

## Capabilities

### New Capabilities
- `entry-native-value`: Define the updated `Entry` data contract where `value` accepts any JSON-compatible type, and specify how native values participate in two-level digest computation.

### Modified Capabilities
- `trucon-two-level-digest`: Digest computation input changes — `value` goes from pre-serialized string to native JSON object within `canonical_json()`. Hash output is identical for the same logical data, but the input representation changes.

## Impact

- **Types**: `src/tc_api/tlog/types.py` — `Entry.value` type annotation change.
- **Digest**: `src/tc_api/tlog_client.py` — `compute_entry_digest()` input handling, `commit_record()` predicate construction.
- **REST callers**: `src/tc_api/main.py`, `src/tc_api/services.py` — remove `json.dumps()` wrappers on all `add_entry()` calls.
- **Docktap**: `docktap/trucon_client.py` — replace `(key, value)` tuples with `Entry` imports, remove `json.dumps()` wrappers.
- **Tests**: `tests/test_two_level_digest.py`, focused unit modules such as `tests/test_tdx_mr_adapter.py`, and `docktap/tests/` — update entry construction and expected digest values.
- **No backward compatibility concern**: no production data exists in the current format.
