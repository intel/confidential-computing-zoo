## Why

The repository currently has a flat layout where tc-api package files (`src/`, `tests/`, `docs/`, `scripts/`, `pyproject.toml`, etc.) live at the repo root alongside three standalone tlog packages (`tlog/`, `tlog-rekor/`, `tlog-onchain/`) and the trust-service (`aa_asr_cdh/`). This makes it impossible to subtree-merge the repo into the future `agent-cc/core/` monorepo — the flat structure would collide with other packages. The repo needs a clear directory hierarchy where each logical unit occupies its own subdirectory.

## What Changes

- **BREAKING**: Move all tc-api package files into a `tc-api/` subdirectory (`src/`, `tests/`, `docs/`, `examples/`, `openspec/`, `scripts/` (tc-api-specific), `pyproject.toml`, `requirements.txt`, `setup.sh`, `start.sh`, `run_tests.sh`, `AGENTS.md`, `README.md`, `.env.example`, `.github/`, `.vscode/`)
- Rename `aa_asr_cdh/` to `trust-service/` for clarity
- Split `scripts/` — system-level orchestration scripts (`dev-up.sh`, `trust_service.sh`, VFS scripts) stay at repo root; tc-api-specific scripts move to `tc-api/scripts/`
- Move stray `tdvm_smoke_test.py` into `tc-api/tests/`
- Remove dead remnants: `docktap/` pycache dirs, `src/tc_api/tlog/` tombstone package
- Update `Dockerfile` to explicitly COPY `tlog/`, `tlog-rekor/`, `tc-api/` instead of `COPY . /app/`
- Update `docker-compose.yml` volume mounts to reference `tc-api/` subdirectory
- Update `scripts/dev-up.sh` paths for renamed `trust-service/` and relocated `start.sh`
- Update `tc-api/setup.sh` to install tlog dependencies from sibling directories
- Create a new root-level `README.md` describing the monorepo structure
- `tlog/`, `tlog-rekor/`, `tlog-onchain/` stay at their current positions (no change)
- No Python import changes — all `from tc_api.*`, `from tlog.*`, `from tlog_rekor.*` imports remain identical

## Capabilities

### New Capabilities
- `monorepo-layout`: Defines the target directory structure where each logical unit (tc-api, tlog packages, trust-service) has its own top-level directory, with system-level files (Dockerfile, docker-compose, deploy/) at the repo root

### Modified Capabilities
- `docktap-package-integration`: Dockerfile and docker-compose paths change for the docktap service
- `tlog-package-layout`: setup.sh install paths change to reference sibling tlog directories

## Impact

- **Build/CI**: Dockerfile build context stays at repo root but COPY paths change; docker-compose volume mounts change
- **Developer workflow**: `setup.sh`, `start.sh`, `run_tests.sh` move to `tc-api/`; developers `cd tc-api` before running them
- **Deployment**: Container ENTRYPOINT and WORKDIR paths update; docker-compose service definitions update
- **Documentation**: Root README becomes monorepo overview; tc-api README moves into subdirectory
- **No API changes**: All HTTP endpoints, Python module paths, and CLI entry points remain identical
- **No import changes**: Zero Python source code modifications needed
