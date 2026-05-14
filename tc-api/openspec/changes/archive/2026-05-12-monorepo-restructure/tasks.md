## 1. Pre-clean Remnants

- [x] 1.1 Remove `docktap/` pycache remnants at repo root (`rm -rf docktap/`)
- [x] 1.2 Remove `src/tc_api/tlog/` tombstone package (`git rm -r src/tc_api/tlog/`)
- [x] 1.3 Move `tdvm_smoke_test.py` into `scripts/` as an operator helper (`git mv tdvm_smoke_test.py scripts/`)

## 2. Create tc-api Subdirectory and Move Files

- [x] 2.1 Create `tc-api/` directory
- [x] 2.2 Move core package files: `git mv src/ tests/ docs/ examples/ openspec/ pyproject.toml requirements.txt AGENTS.md README.md .env.example` into `tc-api/`
- [x] 2.3 Move shell scripts: `git mv setup.sh start.sh run_tests.sh` into `tc-api/`
- [x] 2.4 Move tooling directories: `git mv .github/ .vscode/` into `tc-api/`
- [x] 2.5 Keep tc-api-specific operator helpers under `tc-api/scripts/` (`run_docktap_oob_atomic.py`, `verify_current_attested_head.py`, `tdvm_smoke_test.py`)

## 3. Rename Trust Service

- [x] 3.1 Rename `aa_asr_cdh/` to `trust-service/` (`git mv aa_asr_cdh/ trust-service/`)

## 4. Update Dockerfile

- [x] 4.1 Replace `COPY . /app/` with targeted COPY commands for `tlog/`, `tlog-rekor/`, and `tc-api/`
- [x] 4.2 Change WORKDIR to `/app/tc-api`
- [x] 4.3 Update pip install command to install tlog and tlog-rekor from sibling paths plus tc-api itself
- [x] 4.4 Update ENTRYPOINT/CMD paths (start.sh, venv references) for new WORKDIR

## 5. Update docker-compose.yml

- [x] 5.1 Update tc-api service volume mounts: `./uploads` → `./tc-api/uploads`, `./builds` → `./tc-api/builds`, `./logs` → `./tc-api/logs`
- [x] 5.2 Update trucon service volume mount: `./logs` → `./tc-api/logs`
- [x] 5.3 Update docktap service volume mount: `./logs` → `./tc-api/logs`
- [x] 5.4 Verify all service commands still reference correct Python module paths (tc_api.trucon.app, tc_api.docktap.main)

## 6. Update Orchestration Scripts

- [x] 6.1 Update `scripts/dev-up.sh`: change `$REPO_ROOT/aa_asr_cdh/` to `$REPO_ROOT/trust-service/` and `./start.sh` to `./tc-api/start.sh`

## 7. Update tc-api Internal Paths

- [x] 7.1 Update `tc-api/setup.sh` to install tlog packages from sibling dirs: `pip install -e ../tlog -e ../tlog-rekor -e .`
- [x] 7.2 Review `tc-api/run_tests.sh` for any path references that need updating
- [x] 7.3 Update `tc-api/AGENTS.md` top-level description for new directory structure

## 8. Update .gitignore

- [x] 8.1 Update root `.gitignore` to cover `tc-api/` subdirectory runtime paths (uploads, builds, logs, venv)

## 9. Create Root README

- [x] 9.1 Create a new root `README.md` describing the monorepo structure, listing each top-level directory and its purpose

## 10. Validation

- [x] 10.1 Run `cd tc-api && bash setup.sh` — verify editable install succeeds
- [x] 10.2 Run `cd tc-api && bash run_tests.sh` — verify pytest passes (same as before restructure)
- [x] 10.3 Run `docker-compose build` — verify image builds successfully
- [x] 10.4 Verify no Python import changes were needed (grep for old paths)
