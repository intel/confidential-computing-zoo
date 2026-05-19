# Workspace Root

This repository root is a workspace-level entry point. It currently contains the `tc-api` / trusted-log / trust-service core stack, and this README intentionally documents that stack as a self-contained area rather than trying to describe every sibling directory that may exist here.

## Core Stack Layout

| Directory | Description |
|-----------|-------------|
| `tc-api/` | TC API service — FastAPI application, TruCon sequencer, Docktap proxy, CLI tools, tests, and docs |
| `tlog/` | Standalone trusted-log package — core types/ABCs/digests plus backend namespaces under `tlog.backends.*` |
| `trust-service/` | Attestation trust service — AA, ASR, CDH (Docker-based, independent) |
| `deploy/` | Deployment configuration (nginx) |
| `scripts/` | Cross-service orchestration (`dev-up.sh`, `trust_service.sh`, VFS scripts) |

## Core Stack Entry Points

The root README is intentionally a navigator, not a single quick start.

Start with the README that matches the component you want to work on:

| Subproject | README |
|-----------|--------|
| `tc-api/` | `tc-api/README.md` |
| `tlog/` | `tlog/README.md` |
| `trust-service/` | `trust-service/README.md` |

Typical workflows:

- API / TruCon / Docktap development: work from `tc-api/`
- Trusted-log core and backend work: work from `tlog/`
- Attestation trust stack work: work from `trust-service/`
- Full local stack via containers: use `tc-api/docker-compose.yml`

## Core Stack Workflows

```bash
# Full local stack
cd tc-api
docker-compose build
docker-compose up -d

# API service development
cd tc-api
bash setup.sh
bash run_tests.sh

# Trust-log core and Rekor backend work
cd ../tlog
python -m pip install -e '.[rekor]'
```

## System-Level Files

- `tc-api/docker-compose.yml` — Core-stack local orchestration for tc-api (:8000), trucon (:8001), docktap (:8002)
- `tc-api/Dockerfile` — Container image for the tc-api / consolidated tlog service stack
- `deploy/nginx.conf` — Reverse proxy configuration
