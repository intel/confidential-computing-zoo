## ADDED Requirements

### Requirement: Business endpoints use TrustedLogAPI for event logging
Each business endpoint (build, publish, launch) SHALL use the `TrustedLogAPI` instance from `app.state.trusted_log` instead of constructing a `ChainedTransparencyLog` instance. The endpoint SHALL call `init_record()` at the start of its async workflow, `add_entry(record_id, entry)` at each step, and `commit_record()` once at the end.

#### Scenario: Build endpoint uses TrustedLogAPI
- **WHEN** the build endpoint starts a background build task
- **THEN** it SHALL call `init_record()` on `app.state.trusted_log`, pass the resulting `record_id` through the workflow, and call `commit_record()` after all build steps complete

#### Scenario: Publish endpoint uses TrustedLogAPI
- **WHEN** the publish endpoint starts a background publish task
- **THEN** it SHALL call `init_record()` on `app.state.trusted_log`, accumulate entries via `add_entry()`, and call `commit_record()` after publishing completes

#### Scenario: Launch endpoint uses TrustedLogAPI
- **WHEN** the launch endpoint starts a background launch task
- **THEN** it SHALL call `init_record()` on `app.state.trusted_log`, accumulate entries via `add_entry()`, and call `commit_record()` after launch completes

### Requirement: Entry format uses Entry dataclass
All `add_entry()` calls SHALL use the `Entry(key, value)` dataclass from `trusted_container_log.types`. The `value` field SHALL be a JSON-serialized string when the original data is a dict.

#### Scenario: Dict entry converted to Entry dataclass
- **WHEN** a workflow step produces audit data as `{"build_image": {"status": "success", ...}}`
- **THEN** it SHALL be passed as `Entry(key="build_image", value=json.dumps({"status": "success", ...}))`

### Requirement: DockerService methods accept TrustedLogAPI and record_id
`DockerService` methods that currently accept a `ChainedTransparencyLog` parameter SHALL accept `tlog: TrustedLogAPI` and `record_id: str` parameters instead.

#### Scenario: build_image receives TrustedLogAPI
- **WHEN** `build_image()` is called
- **THEN** it SHALL accept `tlog` (TrustedLogAPI) and `record_id` (str) parameters and use `tlog.add_entry(record_id, Entry(...))` for audit logging

### Requirement: No ChainedTransparencyLog imports in main.py or services.py
After migration, `main.py` and `services.py` SHALL NOT import or reference `ChainedTransparencyLog`.

#### Scenario: Legacy import removed from main.py
- **WHEN** inspecting `main.py` imports
- **THEN** there SHALL be no `from .trusted_container_log import ChainedTransparencyLog` statement

#### Scenario: Legacy import removed from services.py
- **WHEN** inspecting `services.py` imports
- **THEN** there SHALL be no `from .trusted_container_log import ChainedTransparencyLog` statement
