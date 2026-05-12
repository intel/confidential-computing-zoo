## Why

After syncing with the upstream refactor branch, the project has two parallel architecture visions: upstream introduces a "TruCon" service abstraction with Docktap integration and instance mapping, while our branch implements a working split architecture (tc_api + Trust API) with sequencer lock, embedded daemon, and crash recovery. The naming, documentation structure, and several design details are out of sync. A merge is needed to unify terminology, reconcile the two-tier documentation model, and prepare for upstream contribution.

## What Changes

- Rename "Trust API" to "TruCon" across all code, config, and documentation (`trust_api.py` → `trucon.py`, `TRUST_API_URL` → `TRUCON_URL`, `trust_api_url` → `trucon_url`, docker-compose service name, start.sh).
- Adopt two-tier architecture documentation: top-level `architecture.md` as the system-wide vision (REST + Docktap + TruCon topology, deployment model, migration plan), and `trusted-log/architecture.md` as the self-contained implementation-detail document (threading.Lock, SQLite schema, crash recovery, DSSE signing, embedded daemon). The trusted-log docs must remain independent with no upward references, since the module may be extracted as a separate project.
- Update top-level `architecture.md` to reflect our implemented TruCon architecture while preserving upstream's Docktap integration and instance mapping as planned capabilities.
- Document `prev_log_id` chaining as a future secondary ordering method in `trusted-log/architecture.md`. Current implementation (RTMR-based ordering, prev_log_id not in DSSE predicate) remains the default.
- Update `trusted-log/architecture.md`, `trusted-log/api.md`, and `trusted-log/README.md` to use "TruCon" naming consistently.
- Align tests with the rename.

## Capabilities

### New Capabilities
- `trucon-naming-convention`: Define the canonical naming for the TruCon core service across code, config, deployment, and documentation artifacts.
- `trucon-two-tier-docs`: Define the two-tier architecture documentation model — top-level system vision vs trusted-log implementation detail — including boundary rules and cross-reference conventions.

### Modified Capabilities
- `tlog-sequencer`: Update all references from "Trust API" to "TruCon" in sequencer-related behavior and deployment descriptions.
- `tlog-rest-commit`: Update REST endpoint documentation and config parameter names to use TruCon naming.
- `tlog-embedded-submitter`: Update embedded submit daemon references to use TruCon naming.

## Impact

- Affected code: `trust_api.py` (rename to `trucon.py`), `config.py` (`TRUCON_URL`), `main.py`, `trusted_container_log/api.py` (`trucon_url` param), `docker-compose.yml`, `start.sh`, `test_sequencer_refactor.py`, `test_tlog_refactored.py`.
- Affected documentation: `architecture.md` (top-level), `trusted-log/architecture.md`, `trusted-log/api.md`, `trusted-log/README.md`.
- Affected specs: `tlog-sequencer`, `tlog-rest-commit`, `tlog-embedded-submitter` (delta specs for naming updates).
- No external API changes. No behavioral changes. Purely naming, documentation structure, and upstream alignment.
