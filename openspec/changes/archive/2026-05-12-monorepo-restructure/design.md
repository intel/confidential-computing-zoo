## Context

The repository currently has a flat layout where tc-api source files (`src/`, `tests/`, `docs/`, `pyproject.toml`, etc.) sit at the repo root alongside three standalone tlog packages and the trust-service directory. This layout evolved organically as tlog was extracted into its own package but tc-api was never moved into its own subdirectory. The repo is destined to be subtree-merged into `agent-cc/core/`, which requires each logical unit to occupy its own top-level directory.

Current tracked top-level items: `src/`, `tests/`, `docs/`, `examples/`, `openspec/`, `scripts/`, `pyproject.toml`, `requirements.txt`, `setup.sh`, `start.sh`, `run_tests.sh`, `AGENTS.md`, `README.md`, `.env.example`, `.github/`, `.vscode/`, `tlog/`, `tlog-rekor/`, `tlog-onchain/`, `aa_asr_cdh/`, `Dockerfile`, `docker-compose.yml`, `deploy/`, `tdvm_smoke_test.py`.

## Goals / Non-Goals

**Goals:**
- Move all tc-api package files into a `tc-api/` subdirectory
- Rename `aa_asr_cdh/` to `trust-service/` for clarity
- Split `scripts/` into system-level (root) and tc-api-specific (`tc-api/scripts/`)
- Update Dockerfile, docker-compose.yml, and orchestration scripts for new paths
- Remove dead remnants (docktap pycache dirs, tlog tombstone)
- Preserve all Python import paths — zero source code changes
- Preserve all Docker service behavior (same ports, same modules, same entry points)

**Non-Goals:**
- Changing any Python package structure or import paths
- Modifying tlog, tlog-rekor, or tlog-onchain package contents or locations
- Adding CI/CD pipelines or GitHub Actions
- Creating separate Dockerfiles per service
- Changing API endpoints, CLI entry points, or module paths

## Decisions

### D1: tc-api subdirectory name = `tc-api/`

Use `tc-api/` (hyphenated, matching the PyPI package name) rather than `tc_api/` (which would collide with the Python package under `src/tc_api/`) or `api/` (too generic).

*Alternative*: `tc_api/` — rejected because it creates confusion with `src/tc_api/` Python package directory.

### D2: One-shot `git mv` migration

Execute all moves in a single commit using `git mv`. This preserves git history (rename detection) and avoids intermediate broken states.

*Alternative*: Incremental moves across multiple commits — rejected because every intermediate state would have broken Dockerfile/docker-compose paths.

### D3: Dockerfile uses explicit COPY per package

Replace `COPY . /app/` with targeted COPY commands:
```dockerfile
COPY tlog/       /app/tlog/
COPY tlog-rekor/ /app/tlog-rekor/
COPY tc-api/     /app/tc-api/
```

This produces smaller images (excludes `trust-service/`, `tlog-onchain/`, docs, tests) and makes build dependencies explicit. WORKDIR changes to `/app/tc-api`.

*Alternative*: Keep `COPY . /app/` — rejected because it copies unnecessary files and obscures build dependencies.

### D4: setup.sh installs sibling tlog packages

`tc-api/setup.sh` changes from `pip install -e .` to:
```bash
pip install -e "$SCRIPT_DIR/../tlog" -e "$SCRIPT_DIR/../tlog-rekor" -e .
```

This handles the new directory relationship where tlog packages are siblings of `tc-api/` rather than siblings of `src/`.

### D5: System-level files stay at repo root

`Dockerfile`, `docker-compose.yml`, `deploy/nginx.conf`, and cross-service orchestration scripts (`scripts/dev-up.sh`, `scripts/trust_service.sh`, VFS scripts) remain at the repo root because they operate across multiple packages/services.

### D6: .github/ and openspec/ move with tc-api

The `.github/` directory (openspec skills/prompts) and `openspec/` directory are tc-api-specific tooling and move into `tc-api/`. When the repo becomes `agent-cc/core/`, these stay with the tc-api subtree.

### D7: docker-compose volume mounts update to tc-api/ prefix

Runtime directories (`uploads/`, `builds/`, `logs/`) are created inside `tc-api/` at runtime. Volume mounts change from `./uploads:/app/uploads` to `./tc-api/uploads:/app/tc-api/uploads` (or keep `/app/uploads` target with adjusted source).

## Risks / Trade-offs

- **[Developer muscle memory]** → Developers must `cd tc-api` before running `setup.sh`, `start.sh`, `run_tests.sh`. Mitigated by clear root README.
- **[Docker build cache invalidation]** → Switching from `COPY .` to targeted COPYs invalidates all existing cached layers. One-time cost.
- **[git history fragmentation]** → `git log --follow` tracks renames but some tools may not follow by default. Mitigated by using `git mv` which records renames.
- **[scripts/dev-up.sh path breakage]** → References `aa_asr_cdh/` and `./start.sh`. Must update both paths. Mitigated by updating in the same commit.
