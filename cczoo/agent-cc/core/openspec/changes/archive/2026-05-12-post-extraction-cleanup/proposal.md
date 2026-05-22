## Why

The `tlog-extraction-backend-isolation` change extracted shared trusted-log types and the Rekor backend adapter into standalone packages (`tlog/`, `tlog-rekor/`). However, it left behind dead code (duplicate adapter files that were copied but never deleted), orphan shim files, and `docktap/` remains a top-level directory using `sys.path` hacks instead of being a proper sub-package. Before merging into the `agent-cc/core/` monorepo, these structural debts must be resolved so the repo layout is clean and all Python modules follow standard packaging conventions.

## What Changes

- **Delete dead adapter files** — Remove `src/tc_api/trucon/adapters/sigstore.py` and `src/tc_api/trucon/adapters/oci_mirror.py` (duplicates of code now canonical in `tlog-rekor/`). Update 4 test files still importing `OciBundleMirror` from the old path.
- **Delete orphan tlog shim files** — Remove `src/tc_api/tlog/types.py`, `errors.py`, `immutable.py`, `local_mr.py` (compatibility shims with no remaining consumers). Keep `__init__.py` as a tombstone notice.
- **Move `docktap/` into `src/tc_api/docktap/`** — Relocate the entire docktap directory tree into the `tc_api` package so it is a proper sub-package installable via `pip install -e .`.
- **Rewrite docktap internal imports** — Convert ~30 bare module imports (`from trucon_client import ...`, `from proxy.docker_proxy import ...`) to relative imports (`from .trucon_client import ...`). Remove all `sys.path.insert` hacks from `main.py`, `conftest.py`, and test files.
- **Update deployment entry points** — Change `docker-compose.yml` and `start.sh` from `python -m docktap.main` to `python -m tc_api.docktap.main`. Add `tc-docktap` CLI entry point in `pyproject.toml`.
- **BREAKING**: `docktap` module path changes from `docktap.*` to `tc_api.docktap.*`.

## Capabilities

### New Capabilities
- `docktap-package-integration`: Requirements for docktap as a sub-package of `tc_api` with standard relative imports, proper package discovery, and a `tc-docktap` CLI entry point.

### Modified Capabilities
- `tlog-package-layout`: The `trucon/adapters/` directory no longer contains `sigstore.py` or `oci_mirror.py` — those live exclusively in `tlog-rekor`. Update the spec to reflect the final adapter directory contents.

## Impact

- **Code**: ~30 import rewrites in `docktap/` files, 4 test import updates for OciBundleMirror, deletion of 6 dead/shim files.
- **Deployment**: `docker-compose.yml` command path, `start.sh` docktap invocation, and process matching patterns need updating.
- **Build**: `pyproject.toml` gains a `tc-docktap` entry point. No new dependencies.
- **Tests**: `docktap/tests/conftest.py` sys.path hack removed; test files switch to relative or absolute `tc_api.docktap.*` imports. Tests importing from `tc_api.trucon.adapters.oci_mirror` switch to `tlog_rekor.oci_mirror`.
