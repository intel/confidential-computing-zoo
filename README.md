# agent-cc / core

Monorepo for the Trusted Container platform — API service, trusted-log packages, and trust service.

## Repository Layout

| Directory | Description |
|-----------|-------------|
| `tc-api/` | TC API service — FastAPI application, TruCon sequencer, Docktap proxy, CLI tools, tests, and docs |
| `tlog/` | Standalone trusted-log package — domain types, ABCs, digest functions (zero third-party deps) |
| `tlog-rekor/` | Rekor backend adapter — `SigstoreLogAdapter`, `OciBundleMirror` |
| `tlog-onchain/` | On-chain backend adapter (scaffold) |
| `trust-service/` | Attestation trust service — AA, ASR, CDH (Docker-based, independent) |
| `deploy/` | Deployment configuration (nginx) |
| `scripts/` | Cross-service orchestration (`dev-up.sh`, `trust_service.sh`, VFS scripts) |

## Quick Start

```bash
# Development setup
cd tc-api
bash setup.sh       # Creates venv, installs tlog + tlog-rekor + tc-api
bash run_tests.sh    # Run test suite

# Start services
bash start.sh        # Starts tc-api, trucon, docktap

# Docker
docker-compose build   # From repo root
docker-compose up -d
```

## System-Level Files

- `Dockerfile` — Multi-package container image (copies tlog, tlog-rekor, tc-api)
- `docker-compose.yml` — Three services: tc-api (:8000), trucon (:8001), docktap (:8002)
- `deploy/nginx.conf` — Reverse proxy configuration
