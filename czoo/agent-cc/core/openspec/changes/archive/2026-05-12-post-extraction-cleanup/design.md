## Context

The `tlog-extraction-backend-isolation` change successfully extracted `tlog` and `tlog-rekor` as standalone packages but left structural debris: duplicate adapter files in `trucon/adapters/`, orphan compatibility shims in `src/tc_api/tlog/`, and `docktap/` as a top-level directory relying on `sys.path` manipulation instead of proper Python packaging. The codebase needs these issues resolved before merging into `agent-cc/core/`.

Current layout:
```
tc_api/
├── tlog/                          ✅ standalone package
├── tlog-rekor/                    ✅ standalone package
├── tlog-onchain/                  ✅ scaffold
├── docktap/                       ❌ top-level, sys.path hacks
│   ├── main.py                    sys.path.insert(0, __file__dir)
│   ├── trucon_client.py           bare: from proxy.docker_proxy import ...
│   ├── proxy/                     bare: from trucon_client import ...
│   ├── tests/conftest.py          sys.path.insert(0, DOCKTAP_DIR)
│   └── tests/*.py                 bare imports throughout
├── src/tc_api/
│   ├── tlog/                      ❌ dead shim files (types.py, errors.py, ...)
│   └── trucon/adapters/
│       ├── sigstore.py            ❌ dead duplicate (canonical in tlog-rekor)
│       ├── oci_mirror.py          ❌ dead duplicate (canonical in tlog-rekor)
│       ├── tdx_mr.py              ✅ platform adapter
│       ├── tdx_quote.py           ✅ platform adapter
│       └── ccel.py                ✅ platform adapter
```

## Goals / Non-Goals

**Goals:**
- Delete all dead/duplicate files left from the extraction
- Move `docktap/` into `src/tc_api/docktap/` as a proper sub-package
- Eliminate all `sys.path` hacks in docktap code and tests
- Add `tc-docktap` CLI entry point for consistency with `tc-api`, `tc-trucon`, `tc-verify`
- Update deployment files (`docker-compose.yml`, `start.sh`) for new module path

**Non-Goals:**
- Refactoring docktap internal architecture (just moving and fixing imports)
- Extracting shared modules (sigstore_identity, internal_transport) into separate packages
- Changing verify CLI dependencies or splitting config.py
- Altering any runtime behavior or API contracts

## Decisions

### Decision 1: Move docktap into src/tc_api/docktap/ (not a sibling package)

**Choice:** docktap becomes `tc_api.docktap`, a sub-package within the existing `tc_api` install.

**Rationale:** docktap imports 4 modules from `tc_api` internals (`sigstore_identity`, `sigstore_baseline`, `trucon.internal_transport`, `trucon.owner_authorization`). Making it a sibling package would require extracting those modules into shared packages — much larger scope for no practical benefit. Since docktap is always deployed alongside tc_api and trucon, accepting the coupling as internal is pragmatic.

**Alternatives considered:**
- Sibling package with shared module extraction — larger scope, deferred to future if needed
- Keep as top-level with sys.path hacks — violates Python packaging conventions, breaks IDE support

### Decision 2: Convert bare imports to relative imports (not absolute)

**Choice:** Use relative imports within docktap (`from .trucon_client import ...`, `from .proxy.docker_proxy import ...`).

**Rationale:** Relative imports are the Python convention for intra-package references. They don't break if the parent package is renamed, and they make the dependency direction explicit. Absolute imports (`from tc_api.docktap.trucon_client import ...`) would also work but are more verbose and couple to the parent path.

### Decision 3: Add tc-docktap entry point

**Choice:** Add `tc-docktap = "tc_api.docktap.main:main"` to `pyproject.toml [project.scripts]`.

**Rationale:** Matches the existing CLI naming pattern (`tc-api`, `tc-trucon`, `tc-verify`, `tc-client`). Provides a stable invocation path that doesn't require knowing the Python module structure. `docker-compose.yml` and `start.sh` will use this or the equivalent `python -m tc_api.docktap.main`.

### Decision 4: Delete dead files rather than adding deprecation shims

**Choice:** Directly delete `trucon/adapters/sigstore.py`, `trucon/adapters/oci_mirror.py`, and the tlog shim files. No deprecation warnings or re-export stubs.

**Rationale:** No external consumers depend on these paths. All internal imports were already migrated in the extraction change. The files are dead code that creates confusion about which copy is canonical.

## Risks / Trade-offs

- **[Risk] Operator scripts reference `docktap.main`** → Mitigated: grep for `docktap.main` in scripts/ and docs/ to catch all references. The change is internal; no published API for external operators.
- **[Risk] Test discovery breaks after move** → Mitigated: `conftest.py` is updated to remove sys.path hacks; pytest discovers `tc_api.docktap.tests` via the installed package. Run full test suite to validate.
- **[Risk] docker-compose.yml path change breaks deployment** → Mitigated: both `docker-compose.yml` and `start.sh` are updated in the same change. The `tc-docktap` entry point provides a stable alternative.

## Migration Plan

1. Delete dead files (adapters, shims) and fix test imports — no behavioral change
2. `mv docktap/ src/tc_api/docktap/` — physical move
3. Rewrite imports in all moved files — bare → relative
4. Remove sys.path hacks — main.py, conftest.py, test files
5. Update pyproject.toml, docker-compose.yml, start.sh — entry points
6. Run full test suite — validate nothing broke
7. No rollback needed — changes are purely structural with no runtime behavior change

## Open Questions

None — all decisions are mechanical and reversible.
