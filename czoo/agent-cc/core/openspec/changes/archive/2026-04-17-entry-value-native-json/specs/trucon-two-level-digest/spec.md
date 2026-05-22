## MODIFIED Requirements

### Requirement: Entry-level digest computation
The system SHALL compute a per-entry digest as `SHA384(canonical_json({"key": key, "value": value}))` for each entry in a record, where `value` is a native JSON-compatible object (not a pre-serialized string). `canonical_json()` SHALL recursively serialize nested objects with `sort_keys=True` and `separators=(',', ':')`. The result SHALL be formatted as `"sha384:<96-hex-chars>"`. Entry order is significant — reordering entries SHALL produce a different event digest.

#### Scenario: Single entry digest with string value
- **WHEN** `compute_entry_digest("build_id", "bld-abc")` is called with a native string value
- **THEN** the function SHALL return `"sha384:<hex>"` where `<hex>` equals `SHA384(canonical_json({"key": "build_id", "value": "bld-abc"}))`.hexdigest()

#### Scenario: Single entry digest with dict value
- **WHEN** `compute_entry_digest("config", {"dir": "/path", "count": 3})` is called with a native dict value
- **THEN** the function SHALL return `"sha384:<hex>"` where `<hex>` equals `SHA384(canonical_json({"key": "config", "value": {"count": 3, "dir": "/path"}}))`.hexdigest() (keys sorted recursively)

#### Scenario: Entry digest determinism
- **WHEN** `compute_entry_digest(key, value)` is called multiple times with the same arguments
- **THEN** it SHALL return the identical digest string every time

#### Scenario: Dict key ordering does not affect digest
- **WHEN** `compute_entry_digest("x", {"b": 2, "a": 1})` and `compute_entry_digest("x", {"a": 1, "b": 2})` are called
- **THEN** both calls SHALL return the identical digest (canonical_json sorts keys)

### Requirement: DSSE predicate includes entries and entry_digests
The DSSE predicate payload constructed by `commit_record()` SHALL include both `entries` (list of `{"key", "value"}` objects with native JSON values for auditing) and `entry_digests` (list of `"sha384:<hex>"` strings for verification). The `digest` field in the predicate SHALL equal the value returned by `compute_event_digest()`.

#### Scenario: Predicate structure
- **WHEN** `commit_record()` constructs the DSSE predicate
- **THEN** the predicate SHALL contain keys: `event_id`, `event_type`, `created`, `entries`, `entry_digests`, `digest`

#### Scenario: Digest consistency
- **WHEN** the predicate is constructed
- **THEN** `predicate["digest"]` SHALL equal `compute_event_digest(predicate["event_id"], predicate["event_type"], predicate["created"], predicate["entry_digests"])`
