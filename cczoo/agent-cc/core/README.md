# Core Services

This directory contains the shared Agent-CC core service stack referenced from the project root. It is the implementation area for the build-to-runtime integrity path and the common trust infrastructure consumed by adapters.

## Core Services Layout

| Directory | Description |
|-----------|-------------|
| `tc-api/` | Trusted build/publish/launch control path (for build-to-runtime verification and policy enforcement) |
| `tlog/` | Immutable, signed runtime evidence and audit trail |
| `trust-service/` | Shared attestation support service (AA, ASR, CDH) used by the core stack |
| `config/` | Shared operational scripts and configuration such as `dev-up.sh`, `nginx.conf`, encrypted VFS helpers, and trust-service wrapper scripts |
| `openspec/` | Core-scope change proposals, archived changes, and layout specifications |

## Entry Points

Start with the README that matches the component you want to work on:

| Component | README |
|-----------|--------|
| `tc-api/` | `tc-api/README.md` |
| `tlog/` | `tlog/README.md` |
| `trust-service/` | `trust-service/README.md` |

Typical workflows:

- API, TruCon, and Docktap development: work from `tc-api/`
- Trusted-log domain model and backend work: work from `tlog/`
- Attestation container setup and debugging: work from `trust-service/`
- Shared helper scripts and local orchestration: work from `config/`

## Path Status

`trust-service/` remains under `core/` today because the current monorepo layout spec and helper scripts reference that path.

If you want to relocate it under `adapters/`, update `openspec/specs/monorepo-layout/spec.md` and path consumers such as `config/dev-up.sh` first.

## Common Workflows

```bash
# Start or restart tc-api, TruCon, and Docktap
cd tc-api
./start.sh restart

# Start the trust-service container wrapper plus tc-api stack
cd ..
bash core/config/dev-up.sh restart

# Work on the standalone trusted-log package
cd core/tlog
python -m pip install -e '.[rekor]'
```

## System-Level Files

- `config/dev-up.sh` — Starts the trust-service container and then launches the tc-api stack
- `config/nginx.conf` — Shared reverse-proxy configuration kept with the core service assets
- `config/trust_service.sh` — Helper entrypoint for trust-service related local operations
- `config/create_encrypted_vfs.sh` — Encrypted VFS creation helper for lifecycle data protection flows
- `config/mount_encrypted_vfs.sh` and `config/unmount_encrypted_vfs.sh` — Encrypted VFS mount lifecycle helpers
