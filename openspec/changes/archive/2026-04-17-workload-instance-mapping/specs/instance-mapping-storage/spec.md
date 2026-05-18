## ADDED Requirements

### Requirement: CommitRequest accepts optional instance_id
The TruCon `POST /commit` endpoint SHALL accept an optional `instance_id` field in the `CommitRequest` body. When provided, the value SHALL be stored in the `commit_queue` record alongside other commit metadata.

#### Scenario: Commit with instance_id provided
- **WHEN** a caller sends `POST /commit` with `instance_id` set to a non-empty string
- **THEN** the committed record in `commit_queue` SHALL have its `instance_id` column set to the provided value

#### Scenario: Commit without instance_id
- **WHEN** a caller sends `POST /commit` without an `instance_id` field (or with `instance_id: null`)
- **THEN** the committed record in `commit_queue` SHALL have its `instance_id` column set to NULL

#### Scenario: Existing commit flow unchanged
- **WHEN** a caller sends `POST /commit` with all currently required fields and no `instance_id`
- **THEN** the commit SHALL succeed with the same `CommitResponse` shape and behavior as before this change

### Requirement: commit_queue schema includes instance_id column
The `commit_queue` SQLite table SHALL include an `instance_id TEXT` column. A composite index on `(chain_id, instance_id)` SHALL exist for efficient mapping queries.

#### Scenario: Schema migration on startup
- **WHEN** TruCon starts with an existing database that lacks the `instance_id` column
- **THEN** the column SHALL be added via `ALTER TABLE` without data loss, and the composite index SHALL be created

#### Scenario: New database creation
- **WHEN** TruCon starts with no existing database
- **THEN** the `commit_queue` table SHALL include `instance_id TEXT` in its CREATE TABLE DDL, and the composite index SHALL be created
