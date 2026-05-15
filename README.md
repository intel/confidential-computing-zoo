# Workspace Root

This repository root is a workspace-level entry point. It currently contains the `tc-api` / trusted-log / trust-service core stack, and this README intentionally documents that stack as a self-contained area rather than trying to describe every sibling directory that may exist here.

## Core Stack Layout

| Directory | Description |
|-----------|-------------|
| `tc-api/` | TC API service — FastAPI application, TruCon sequencer, Docktap proxy, CLI tools, tests, and docs |
| `tlog/` | Standalone trusted-log package — domain types, ABCs, digest functions (zero third-party deps) |
| `tlog-rekor/` | Rekor backend adapter — `SigstoreLogAdapter`, `OciBundleMirror` |
| `tlog-onchain/` | On-chain backend adapter (scaffold) |
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
| `tlog-rekor/` | `tlog-rekor/README.md` |
| `tlog-onchain/` | `tlog-onchain/README.md` |
| `trust-service/` | `trust-service/README.md` |

Typical workflows:

- API / TruCon / Docktap development: work from `tc-api/`
- Trusted-log core types and digest logic: work from `tlog/`
- Rekor adapter and OCI mirror work: work from `tlog-rekor/`
- On-chain adapter scaffold work: work from `tlog-onchain/`
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

# Trust-log core package work
cd ../tlog
python -m pip install -e .

# Rekor backend adapter work
cd ../tlog-rekor
python -m pip install -e .
```

## System-Level Files

- `tc-api/docker-compose.yml` — Core-stack local orchestration for tc-api (:8000), trucon (:8001), docktap (:8002)
- `tc-api/Dockerfile` — Container image for the tc-api / tlog / tlog-rekor service stack
- `deploy/nginx.conf` — Reverse proxy configuration
