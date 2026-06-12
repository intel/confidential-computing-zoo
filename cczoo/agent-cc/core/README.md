# Agent-CC Core Services

This directory contains the shared Agent-CC core service stack referenced from the project root. It is the implementation area for the build-to-runtime integrity path and the common trust infrastructure consumed by adapters.

## Core Services Layout

| Directory | Description |
|-----------|-------------|
| `tc_api/` | Trusted build/publish/launch control path (for build-to-runtime verification and policy enforcement) |
| `tlog/` | Immutable, signed runtime evidence and audit trail |
| `trust-service/` | Shared attestation support service (AA, ASR, CDH) used by the core stack |
| `config/` | Shared operational scripts and configuration such as `dev-up.sh`, `nginx.conf`, encrypted VFS helpers, and trust-service wrapper scripts |
| `openspec/` | Core-scope change proposals, archived changes, and layout specifications |
