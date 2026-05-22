## ADDED Requirements

### Requirement: Entry value accepts any JSON-compatible type
The `Entry` dataclass SHALL define `value` as accepting any JSON-compatible Python type: `str`, `dict`, `list`, `int`, `float`, `bool`, or `None`. Callers MUST NOT wrap values in `json.dumps()` before passing them to `Entry`.

#### Scenario: String value
- **WHEN** an `Entry` is created with `Entry(key="build_id", value="bld-3bdb633")`
- **THEN** the entry SHALL store the string directly without additional encoding

#### Scenario: Dict value
- **WHEN** an `Entry` is created with `Entry(key="config", value={"config_dir": "/path", "config_count": 3})`
- **THEN** the entry SHALL store the dict as a native Python object

#### Scenario: List value
- **WHEN** an `Entry` is created with `Entry(key="hashes", value=["abc", "def"])`
- **THEN** the entry SHALL store the list as a native Python object

#### Scenario: Numeric and boolean values
- **WHEN** an `Entry` is created with `Entry(key="exit_code", value=0)` or `Entry(key="success", value=True)`
- **THEN** the entry SHALL store the native int or bool value

#### Scenario: None value
- **WHEN** an `Entry` is created with `Entry(key="error", value=None)`
- **THEN** the entry SHALL store `None` as the value

#### Scenario: Non-JSON-serializable value rejected at commit
- **WHEN** a caller creates an `Entry` with a non-JSON-serializable value (e.g., a `datetime` object) and `commit_record()` is called
- **THEN** the system SHALL raise a `TypeError` during digest computation

### Requirement: DSSE predicate entries contain native JSON values
The DSSE predicate `entries` array SHALL serialize entry values as native JSON values, not as escaped JSON strings. The predicate MUST contain a single encoding layer.

#### Scenario: Dict value in predicate
- **WHEN** an entry has `key="config"` and `value={"dir": "/path", "count": 3}`
- **THEN** the predicate SHALL contain `{"key": "config", "value": {"dir": "/path", "count": 3}}` (native object, not escaped string)

#### Scenario: String value in predicate
- **WHEN** an entry has `key="build_id"` and `value="bld-abc"`
- **THEN** the predicate SHALL contain `{"key": "build_id", "value": "bld-abc"}` (plain string, not `"\"bld-abc\""`)

### Requirement: Docktap uses Entry objects from tc_api.tlog.types
Docktap's `trucon_client.py` SHALL import `Entry` from `tc_api.tlog.types` and use `Entry` objects instead of `(key, value)` tuples. All entry construction in `_build_entries()` SHALL return `List[Entry]`.

#### Scenario: Docktap pull event entries
- **WHEN** Docktap captures a `pull` operation
- **THEN** `_build_entries()` SHALL return a list of `Entry` objects with native values (e.g., `Entry(key="image_name", value="nginx")`)

#### Scenario: Docktap predicate construction
- **WHEN** Docktap builds the DSSE predicate for a commit
- **THEN** `entries` SHALL be serialized as `[{"key": e.key, "value": e.value} for e in entries]` using the `Entry` objects

### Requirement: Entry key typo corrections
All entry key strings across the codebase SHALL use correct English spelling. The key `"verfiy_sbom_status"` SHALL be renamed to `"verify_sbom_status"`.

#### Scenario: Corrected key name
- **WHEN** `add_entry()` is called for SBOM verification status
- **THEN** the entry key SHALL be `"verify_sbom_status"`, not `"verfiy_sbom_status"`
