## Context

Documentation has already started using docktap as the canonical product name, but the repository layout still uses the directory name sock-bridge. This causes confusion and leaves command examples, tests, and references split between names.

A folder rename is cross-cutting because many paths across scripts, tests, markdown docs, and OpenSpec artifacts depend on the current directory name.

## Goals / Non-Goals

**Goals:**

- Rename the folder from sock-bridge to docktap.
- Update in-repo references so commands and docs are consistent with the new folder name.
- Keep runtime behavior unchanged except for path/reference updates.
- Provide a clear validation and rollback plan for path migration.

**Non-Goals:**

- Rewriting architecture or proxy behavior unrelated to naming.
- Introducing new runtime features.
- Renaming unrelated repository directories.

## Decisions

1. Physical directory rename is in scope
- Decision: this change includes actual filesystem rename from `sock-bridge/` to `docktap/`.
- Rationale: identity-only docs rename is incomplete without executable path alignment.
- Alternative considered: keep old directory and only update docs. Rejected because it preserves long-term inconsistency.

2. Reference updates are explicit and scoped
- Decision: update references in docs, tests, OpenSpec artifacts, and scripts where `sock-bridge/` path is used.
- Rationale: avoids hidden breakage after folder move.
- Alternative considered: rely on ad hoc fixes after rename. Rejected due to high break risk.

3. Compatibility note over compatibility shim
- Decision: provide migration notes for consumers to use new path rather than maintaining duplicate directory aliases.
- Rationale: keeps repository clean and avoids long-term legacy burden.
- Alternative considered: create symlink alias `sock-bridge -> docktap`. Rejected as non-portable and easy to forget in CI.

4. Verification gate before completion
- Decision: run search-based audits and existing test suite commands from new path to verify migration integrity.
- Rationale: path migrations often fail due to missed references.
- Alternative considered: manual confidence only. Rejected for insufficient reliability.

## Risks / Trade-offs

- [Risk] Missed hardcoded path references break tests/docs.
  -> Mitigation: exhaustive grep audit before and after rename plus targeted test execution.

- [Risk] External automation outside repo may still use old path.
  -> Mitigation: include migration note in change outputs and README updates.

- [Risk] OpenSpec artifacts from prior changes still contain old path examples.
  -> Mitigation: update active change artifacts where appropriate and document intentional historical exceptions.

## Migration Plan

1. Inventory all repository references to `sock-bridge` paths.
2. Rename folder to `docktap`.
3. Apply path reference updates in markdown, tests, and OpenSpec artifacts.
4. Run validation commands from new path.
5. Document retained historical references (if any) and migration notes.

## Implementation Notes

- Renamed the top-level directory from `sock-bridge/` to `docktap/`.
- Updated active runtime/documentation path references and user-facing strings under the renamed folder.
- Updated active OpenSpec implementation notes that referenced live `sock-bridge/...` paths to use `docktap/...`.
- Saved a migration checklist and validation note at `local/docktap-folder-rename-checklist.md`.

Validation snapshot:

- `grep -RIn --exclude-dir=.git --exclude-dir=.pytest_cache --exclude-dir=builds --exclude-dir=uploads --exclude-dir=logs "sock-bridge" .` now returns only intentional checklist/OpenSpec historical references.
- `pytest -q docktap/tests` -> 15 passed, 4 existing `PytestReturnNotNoneWarning` warnings in legacy tests.
- `python docktap/test_suite.py all` -> 8/8 passed.

Retained references and justification:

- Change names and capability IDs that include `sock-bridge` remain unchanged to preserve artifact identity/history.
- Proposal/design text that describes the migration from `sock-bridge` to `docktap` intentionally retains the old name as source context.
- Generated cache files are excluded from migration scope and validation.

## Open Questions

- Should this change also rename Python import package roots if directory rename impacts import resolution expectations?
- Do we want a short transitional release note listing old-to-new command examples for users?
