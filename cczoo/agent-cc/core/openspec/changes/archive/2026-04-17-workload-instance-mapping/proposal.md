## Why

TruCon records trusted events from both REST API and Docktap sources, but has no structured way to correlate those events to workloads and container instances. With GAP-01 (Docktap→TruCon emission) and GAP-11 (per-workload chain assignment) completed, runtime events are recorded and routed to per-workload chains — but audit and verification tooling cannot answer "which instances ran under workload X?" or "what events occurred for container Y?" This is the final piece needed to make the Docktap integration auditable end-to-end.

## What Changes

- Add `instance_id` (= Docker container ID) as an optional metadata field on `CommitRequest`, stored alongside each commit record in the TruCon SQLite queue.
- Create TruCon query endpoints for workload→instance and instance→event lookups.
- Docktap passes `container_id` as `instance_id` in every commit to TruCon.
- REST API callers may optionally include `instance_id` when relevant.
- Resolve open architecture question Q-03: canonical instance identity is the full 64-character Docker `container_id`, representing one `create→rm` lifecycle.

## Capabilities

### New Capabilities
- `instance-mapping-storage`: TruCon stores `instance_id` per commit record and maintains workload→instance→event correlation data in SQLite.
- `instance-mapping-query`: TruCon exposes REST endpoints to query workload instances and instance events (`GET /workloads/{id}/instances`, `GET /instances/{id}/events`, `GET /workloads/{id}/events`).
- `instance-metadata-submission`: Docktap and tc_api attach `instance_id` to `CommitRequest` when submitting events to TruCon.

### Modified Capabilities
<!-- No existing spec-level capabilities are changing in requirements. -->

## Impact

- **TruCon API** (`src/tc_api/trucon/app.py`): New query endpoints; `CommitRequest` model extended with optional `instance_id`.
- **TruCon database** (`src/tc_api/trucon/database.py`): `commit_queue` schema gains `instance_id TEXT` column; new query functions for mapping lookups.
- **TruCon models** (`src/tc_api/tlog/types.py`): `CommitRequest` / related types updated.
- **Docktap client** (`docktap/trucon_client.py`): Passes `container_id` as `instance_id` on commit calls.
- **tc_api client** (`src/tc_api/tlog_client.py`): Accepts optional `instance_id` parameter in commit helper.
- **Architecture docs**: `docs/overview_tasks.md` updated to reflect Q-03 resolution and GAP-03 design decisions. `docs/architecture.md` §5.2 mapping model section updated from "Planned" to concrete design.
