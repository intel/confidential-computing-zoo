## 1. Schema & Storage Layer

- [x] 1.1 Add `instance_id TEXT` column to `commit_queue` DDL in `database.py` (both CREATE TABLE and ALTER TABLE migration path)
- [x] 1.2 Create composite index `idx_commit_queue_instance ON commit_queue (chain_id, instance_id)`
- [x] 1.3 Update `insert_record()` in `database.py` to accept and store `instance_id` parameter

## 2. Commit API Extension

- [x] 2.1 Add `instance_id: Optional[str] = None` to `CommitRequest` model in `app.py`
- [x] 2.2 Pass `instance_id` through the commit flow to `insert_record()` in the sequencer

## 3. Query Database Functions

- [x] 3.1 Add `get_instances_for_workload(chain_id)` query in `database.py` — returns distinct instance_id with first/last event timestamps and event count
- [x] 3.2 Add `get_events_for_instance(instance_id)` query in `database.py` — returns records ordered by sequence_num
- [x] 3.3 Add `get_events_for_workload(chain_id)` query in `database.py` — returns all records for a chain ordered by sequence_num

## 4. Query Endpoints

- [x] 4.1 Implement `GET /workloads/{workload_id}/instances` endpoint in `app.py` with `InstanceSummary` response model
- [x] 4.2 Implement `GET /instances/{instance_id}/events` endpoint in `app.py` with `EventSummary` response model
- [x] 4.3 Implement `GET /workloads/{workload_id}/events` endpoint in `app.py` with `EventSummary` response model

## 5. Client-Side Submission

- [x] 5.1 Update `_post_to_trucon()` in `docktap/trucon_client.py` to include `instance_id` (container_id) in commit payload for container lifecycle events (`create`/`start`/`stop`/`rm`) and `null` for `pull`
- [x] 5.2 Update `_post_to_trucon()` in `src/tc_api/tlog_client.py` to accept and forward optional `instance_id` parameter
- [x] 5.3 Thread `instance_id` parameter through `commit_record()` in `tlog_client.py`

## 6. Tests

- [x] 6.1 Unit tests for schema migration (new DB and existing DB without column)
- [x] 6.2 Unit tests for commit with and without `instance_id`
- [x] 6.3 Unit tests for `GET /workloads/{workload_id}/instances` (populated, empty, null-instance exclusion)
- [x] 6.4 Unit tests for `GET /instances/{instance_id}/events` (populated, unknown instance)
- [x] 6.5 Unit tests for `GET /workloads/{workload_id}/events` (cross-instance, includes null-instance records)
- [x] 6.6 Unit tests for Docktap instance_id submission (container events vs pull)
- [x] 6.7 Run full regression suite (`bash run_tests.sh`)

## 7. Documentation Updates

- [x] 7.1 Update `docs/overview_tasks.md` — mark Q-03 resolved, update GAP-03 with design decisions and status
- [x] 7.2 Update `docs/architecture.md` §5.2 — replace "Planned" mapping model with concrete design
- [x] 7.3 Update `docs/architecture.md` §12 — mark Q-03 as resolved in open questions
