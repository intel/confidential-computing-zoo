## Context

A naming update has been requested to replace `sock-bridge` with `docktap` across relevant product documentation and OpenSpec artifacts. The objective is clearer product identity while keeping behavior and architecture unchanged.

This change is primarily documentation and naming consistency work, but it can touch many files and references. A controlled rename strategy is required to avoid partial naming drift and broken references.

## Goals / Non-Goals

**Goals:**

- Establish `docktap` as the canonical product name in markdown documentation under targeted scopes.
- Update OpenSpec change artifacts and related specs/docs to use `docktap` terminology consistently.
- Preserve technical meaning and avoid accidental runtime behavior changes.
- Provide validation steps to detect leftover `sock-bridge` references in targeted docs.

**Non-Goals:**

- Refactoring runtime package/module names unless explicitly requested in a separate implementation change.
- Renaming filesystem directories and import paths in this proposal by default.
- Changing protocol behavior, API contracts, or proxy logic.

## Decisions

1. Canonical naming target
- Decision: `docktap` is the canonical user-facing product name for this scope.
- Rationale: short, Docker-associated, and semantically aligned with traffic tapping/observation.
- Alternative considered: `docktrust` and `dockertap`; rejected for this change to avoid ambiguity in chosen identity.

2. Scope-first rename strategy
- Decision: first update markdown documentation in `docktap/` and `openspec/` where `sock-bridge` appears as product identity; defer code/package/path renames unless separately requested.
- Rationale: minimizes break risk while satisfying naming clarity objective.
- Alternative considered: full repo-wide rename immediately. Rejected due to higher risk of unintended path/import breakage.

3. Reference safety policy
- Decision: retain technical literals that must stay unchanged (for example historical IDs, quoted command outputs, or path references that still exist) and only rename identity-oriented wording.
- Rationale: prevents doc drift from actual executable paths.
- Alternative considered: blind global replacement. Rejected due to high false-positive risk.

4. Verification gate
- Decision: after edits, run targeted search checks for leftover identity references and manually review exceptions.
- Rationale: ensures consistency and catches misses early.
- Alternative considered: rely on manual reading only. Rejected for poor scalability.

## Risks / Trade-offs

- [Risk] Over-aggressive replacement may break path-accurate docs.
  -> Mitigation: distinguish identity text from literal path/code references and review each exception list.

- [Risk] Partial rename may leave mixed naming in non-targeted areas.
  -> Mitigation: document scope boundaries and follow up with additional rename change if needed.

- [Risk] Users may assume runtime binaries/directories were renamed.
  -> Mitigation: explicitly state this change is naming/docs scoped unless implementation tasks include code/path rename.

## Migration Plan

1. Inventory all markdown references containing `sock-bridge` under `docktap/` and `openspec/`.
2. Apply controlled replacements to `docktap` for identity-oriented text.
3. Re-check references and validate that technical path literals are still correct.
4. Summarize renamed files and any intentionally preserved legacy mentions.

## Open Questions

- Should this change include filesystem directory rename (`sock-bridge/` -> `docktap/`) in the same scope or in a dedicated follow-up change?
- Should CLI examples and environment variable names be rebranded now or preserved for compatibility?

## Implementation Notes

Renamed identity-oriented documentation text to `docktap` in targeted scopes:

- `docktap/README.md`
- `docktap/architecture.md`
- `docktap/tools/README.md`
- `openspec/changes/normalize-sock-bridge-lifecycle-classification/proposal.md`
- `openspec/changes/normalize-sock-bridge-lifecycle-classification/specs/sock-bridge-lifecycle-classification/spec.md`

Validation command used:

- `find docktap openspec -type f -name "*.md" -print0 | xargs -0 grep -n "sock-bridge"`

Retained references and justification:

- Literal filesystem paths were updated once the directory rename was completed in the follow-up folder migration change.
- Existing OpenSpec change names/capability IDs containing `sock-bridge` were preserved to avoid breaking artifact identity/history (`rename-sock-bridge-to-docktap`, `normalize-sock-bridge-lifecycle-classification`, `sock-bridge-lifecycle-classification`).
- Rename-change artifacts intentionally mention `sock-bridge` in "from -> to" statements to describe migration context.
