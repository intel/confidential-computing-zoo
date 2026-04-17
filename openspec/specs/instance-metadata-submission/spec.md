## ADDED Requirements

### Requirement: Docktap passes container_id as instance_id
Docktap's TruCon commit call SHALL include the Docker container's full 64-character `container_id` as the `instance_id` field in the `CommitRequest` payload.

#### Scenario: Container lifecycle event submission
- **WHEN** Docktap intercepts a `create`, `start`, `stop`, or `rm` operation for container `abc123...` (64 chars)
- **THEN** the `POST /commit` request to TruCon SHALL include `"instance_id": "abc123..."` (full 64-character container ID)

#### Scenario: Pull operation has no instance_id
- **WHEN** Docktap intercepts a `pull` operation (which is image-level, not container-level)
- **THEN** the `POST /commit` request to TruCon SHALL have `instance_id` set to `null` or omitted

### Requirement: tc_api commit helper accepts optional instance_id
The `tlog_client.py` commit flow SHALL accept an optional `instance_id` parameter and forward it to TruCon in the `CommitRequest`.

#### Scenario: REST caller provides instance_id
- **WHEN** a REST API caller invokes `commit_record()` with `instance_id="container_xyz"`
- **THEN** the `POST /commit` to TruCon SHALL include `"instance_id": "container_xyz"`

#### Scenario: REST caller omits instance_id
- **WHEN** a REST API caller invokes `commit_record()` without specifying `instance_id`
- **THEN** the `POST /commit` to TruCon SHALL omit the `instance_id` field or send it as `null`
