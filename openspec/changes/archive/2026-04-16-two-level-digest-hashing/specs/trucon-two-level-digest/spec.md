## ADDED Requirements

### Requirement: Entry-level digest computation
The system SHALL compute a per-entry digest as `SHA384(canonical_json({"key": key, "value": value}))` for each entry in a record. The result SHALL be formatted as `"sha384:<96-hex-chars>"`. Entry order is significant — reordering entries SHALL produce a different event digest.

#### Scenario: Single entry digest
- **WHEN** `compute_entry_digest("image_hash", "sha256:abc123")` is called
- **THEN** the function SHALL return `"sha384:<hex>"` where `<hex>` equals `SHA384(canonical_json({"key": "image_hash", "value": "sha256:abc123"}))`.hexdigest()

#### Scenario: Entry digest determinism
- **WHEN** `compute_entry_digest(key, value)` is called multiple times with the same arguments
- **THEN** it SHALL return the identical digest string every time

### Requirement: Event-level digest computation
The system SHALL compute the event digest as `SHA384(canonical_json({"created": created_iso, "entry_digests": [...], "event_id": event_id, "event_type": event_type}))`. The input object uses `sort_keys=True` canonical form. The result SHALL be formatted as `"sha384:<96-hex-chars>"`. The event digest SHALL be computed from entry digests, NOT from raw entry content.

#### Scenario: Event digest from entry digests
- **WHEN** `compute_event_digest(event_id, event_type, created_iso, entry_digests)` is called
- **THEN** the function SHALL return `"sha384:<hex>"` computed over the canonical JSON of `{event_id, event_type, created, entry_digests}`

#### Scenario: Empty entries
- **WHEN** a record has zero entries and `compute_event_digest` is called with an empty `entry_digests` list
- **THEN** the function SHALL compute a valid digest over `{event_id, event_type, created, []}`

#### Scenario: Entry order sensitivity
- **WHEN** two records have the same entries in different order
- **THEN** their event digests SHALL differ

### Requirement: DSSE predicate includes entries and entry_digests
The DSSE predicate payload constructed by `commit_record()` SHALL include both `entries` (list of `{"key", "value"}` objects for auditing) and `entry_digests` (list of `"sha384:<hex>"` strings for verification). The `digest` field in the predicate SHALL equal the value returned by `compute_event_digest()`.

#### Scenario: Predicate structure
- **WHEN** `commit_record()` constructs the DSSE predicate
- **THEN** the predicate SHALL contain keys: `event_id`, `event_type`, `created`, `entries`, `entry_digests`, `digest`

#### Scenario: Digest consistency
- **WHEN** the predicate is constructed
- **THEN** `predicate["digest"]` SHALL equal `compute_event_digest(predicate["event_id"], predicate["event_type"], predicate["created"], predicate["entry_digests"])`
