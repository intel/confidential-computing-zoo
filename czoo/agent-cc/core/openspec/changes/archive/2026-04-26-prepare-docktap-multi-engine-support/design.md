## Context

Docktap currently assumes Docker at nearly every layer: proxy naming, daemon socket defaults, lifecycle classification helpers, and runtime event naming. That works for the current deployment, but it means future Podman support would require touching transport parsing, commit payload construction, and verifier semantics at the same time.

The repository already has stable contracts for Docktap lifecycle classification, TruCon runtime commits, and verification profiles. Those contracts are valuable because they define auditable runtime semantics and operator-visible verdicts. The design therefore needs to create a clean engine boundary without fragmenting those existing contracts into multiple profile names or per-engine event schemas.

The most important constraint is simplicity. This change is not the full Podman implementation. It is the preparatory contract and architecture work that keeps Docker behavior intact while making a future second engine a bounded extension rather than a cross-cutting rewrite.

## Goals / Non-Goals

**Goals:**
- Introduce a single runtime-engine abstraction boundary inside Docktap.
- Keep one canonical lifecycle model for auditable runtime operations across engines.
- Require all auditable runtime events to declare `runtime_engine`.
- Keep one `docktap-runtime` verification profile with a small engine-aware rule layer.
- Define simple verifier semantics for missing versus unknown `runtime_engine` values.
- Preserve the current Docker runtime path as the baseline implementation and compatibility target.

**Non-Goals:**
- Implement full Podman runtime support in this change.
- Redesign TruCon sequencing or the broader trusted-log event model.
- Split runtime verification into separate public profiles per engine.
- Rename existing lifecycle operations away from `pull`, `create`, `start`, `stop`, and `rm`.
- Introduce profile version markers unless future rule growth makes historical interpretation ambiguous.

## Decisions

### 1. Add a runtime adapter seam, not a full engine-neutral rewrite
- Decision: Docktap will gain an internal runtime-engine abstraction that normalizes engine-specific request parsing and lifecycle mapping into the existing canonical runtime operations.
- Rationale: this is the smallest architectural move that prevents Docker assumptions from leaking everywhere else.
- Alternative considered: a full engine-neutral rewrite of all Docktap naming and data structures. Rejected because it increases migration cost without improving the immediate future-Podman path.

### 2. Keep canonical lifecycle semantics stable across engines
- Decision: auditable runtime operations remain `pull`, `create`, `start`, `stop`, and `rm`, regardless of the underlying engine.
- Rationale: the existing TruCon commit contract, runtime verification profile, and operator understanding already revolve around these lifecycle semantics.
- Alternative considered: introduce per-engine operation taxonomies. Rejected because it would complicate both verification and cross-engine reasoning.

### 3. Make `runtime_engine` mandatory on all auditable runtime events
- Decision: every auditable Docktap runtime commit will include `runtime_engine`, including Docker-originated events.
- Rationale: a uniform event schema is simpler than conditional presence rules and gives the verifier an explicit dispatch key.
- Alternative considered: emit `runtime_engine` only for non-Docker engines. Rejected because absence would become overloaded and ambiguous.

### 4. Keep one mixed-engine runtime verification profile
- Decision: `docktap-runtime` remains one public profile. Verification runs shared core checks first, then a small engine-aware rule layer selected by `runtime_engine`.
- Rationale: this preserves a simple operator-facing model while allowing engine-specific validation details to grow incrementally.
- Alternative considered: separate profiles such as `docktap-runtime-docker` and `docktap-runtime-podman`. Rejected because profile sprawl is unnecessary at this stage.

### 5. Treat unknown engines as incomplete, not failed
- Decision: missing `runtime_engine` is a hard profile failure; unknown-but-present `runtime_engine` values yield an `incomplete` profile result.
- Rationale: missing data is a producer contract violation, while an unknown engine usually means verifier capability lag rather than bad evidence.
- Alternative considered: fail hard on unknown engine values. Rejected because it would conflate unsupported verifier capability with semantic evidence failure.

### 6. Avoid profile version markers for now
- Decision: do not add an explicit runtime profile version field in this change.
- Rationale: the project can keep one compact profile as long as new engine-specific checks remain additive and do not reinterpret historical evidence.
- Alternative considered: add `profile_version` preemptively. Rejected because it adds coordination overhead before there is actual compatibility ambiguity.

## Risks / Trade-offs

- [Risk] The new abstraction becomes nominal only, with Docker-specific logic still leaking through multiple helpers. -> Mitigation: define explicit adapter responsibilities in the spec and keep lifecycle, commit, and verifier contracts downstream of that boundary.
- [Risk] Future Podman semantics may not map cleanly to the existing lifecycle vocabulary. -> Mitigation: preserve the canonical operation set but allow engine-specific parsing and supplemental checks where semantics differ.
- [Risk] Operators may misread `incomplete` for unknown engines as a passing state. -> Mitigation: document the distinction clearly and require verifier output to explain that engine-specific validation was unavailable.
- [Risk] Skipping a profile version marker now could make later compatibility work harder. -> Mitigation: explicitly state the trigger for adding one: a future change that would reinterpret old valid evidence or introduce new hard-required fields.

## Migration Plan

1. Define the runtime-engine abstraction and event-contract requirements in OpenSpec.
2. Update Docktap runtime commit requirements so `runtime_engine` is mandatory on all auditable events.
3. Update runtime verification requirements to require `runtime_engine`, treat missing values as failed, and treat unknown values as incomplete.
4. Implement Docker as the first adapter-backed engine without changing its externally visible lifecycle semantics.
5. Add test coverage for Docker baseline behavior plus fixture-driven unknown-engine verification outcomes.
6. Introduce Podman-specific parsing and validation only after the abstraction and verifier contracts are in place.

Rollback strategy:
- If the new contract proves too disruptive during implementation, keep the adapter seam design work but temporarily treat missing `runtime_engine` as a warning for historical Docker-only events while the producer path catches up.
- Do not split the verification profile name as a rollback mechanism; use temporary compatibility behavior instead.

## Open Questions

- Which `runtime_engine` values are canonical in v1 (`docker`, `podman`) and how strict should normalization be for aliases?
- How much engine-specific metadata, if any, should be exposed beyond `runtime_engine` before there is a concrete second engine implementation?
- Should unknown-engine `incomplete` verdicts carry a dedicated machine-readable reason code in verifier output?
