## Context

The repository already implements the structural parts of verification: TruCon sequences commits, immutable-backend replay is available, attested-head evidence can be exported, and `tc-verify` can validate replay plus evidence association. The remaining gap is application-layer meaning. Producers in `src/tc_api/main.py`, `src/tc_api/services.py`, and `docktap/trucon_client.py` emit events that are useful for debugging, but they do not yet form a frozen audit contract that lets operators answer whether a given build, publish, launch, or runtime sequence contains the minimum required security facts.

This change is cross-cutting because it affects REST event producers, Docktap runtime event producers, and the operator-facing verification surface. It also has security significance because the profile contract determines what facts are treated as audit-critical, what omissions are hard failures, and how a verifier groups related events.

## Goals / Non-Goals

**Goals:**
- Freeze canonical verification profiles for `build`, `publish`, `launch`, and `docktap-runtime`.
- Define the minimum required audit fields, warning-only omissions, and hard-fail conditions for each profile.
- Reuse the existing `launch_id` as the v1 launch-attempt boundary, and make that boundary explicit in launch verification.
- Align REST and Docktap event payloads with the profile contract so `tc-verify` can evaluate them deterministically.
- Extend `tc-verify` to report profile-scoped verdicts instead of one synthesized workload verdict.

**Non-Goals:**
- Introduce a new external verifier service or policy DSL.
- Redesign TruCon sequencing, evidence export, or immutable-backend replay.
- Support historical compatibility rules for pre-profile chains; the project is still pre-production.
- Model post-launch runtime security behavior beyond the audited event fields already emitted into the chain.

## Decisions

### Reuse `launch_id` as the v1 launch-attempt identity
The design reuses the existing `launch_id` rather than creating a separate `launch_attempt_id`.

Rationale:
- `launch_id` already exists in the REST API, launch result queries, launch evidence, and trusted-log entries.
- The current runtime shape is one launch API invocation to one launch workflow, so introducing a parallel attempt identifier would duplicate identity without resolving a proven one-to-many problem.
- Audit ambiguity today comes from missing propagation and grouping, not from a missing second identifier namespace.

Alternatives considered:
- Add a new `launch_attempt_id`: rejected for v1 because it adds concept duplication without a demonstrated need for one launch request to contain multiple attempts.
- Use `record_id` as the attempt boundary: rejected because `record_id` is a per-commit internal identifier, not a stable business-level audit identity spanning related events.

### Verification is profile-driven, not workload-global
`tc-verify` will evaluate discrete profiles (`build`, `publish`, `launch`, `docktap-runtime`) and report separate verdicts.

Rationale:
- Security audit questions are flow-specific. The evidence needed to judge build integrity is not the same as the evidence needed to judge launch risk.
- A single synthesized workload verdict hides which part of the chain is incomplete or non-compliant.

Alternatives considered:
- Keep one global verdict: rejected because it collapses build, publish, launch, and runtime semantics into an opaque summary.

### Launch verification groups the latest launch-related event set by `launch_id`
For v1, launch verification will select the latest `launch_id` within the workload chain and evaluate the launch-related event set attributed to that identifier.

Rationale:
- This matches the audit question discussed with the user: review the most recent launch attempt for the workload.
- It provides a deterministic grouping rule without inventing a new identity model.

Alternatives considered:
- Group by latest `instance_id`: rejected because pre-create failures have no instance identity and because a launch attempt may involve more than one relevant event before instance creation is complete.
- Group by timestamp proximity: rejected because it is heuristic and hard to justify in an audit report.

### Producers emit both stable identities and auditable security projections
Profiles will require stable object identities such as OCI digest and explicit security-relevant projections such as launch privilege settings.

Rationale:
- Digest-only contracts are good for equality checks but poor for human auditability.
- Raw logs alone are too loose and unstable to serve as verifier input.

Implications by flow:
- `build`: requires digest identity for outputs and a bounded set of build input digests.
- `publish`: starts simple, but still requires the pushed subject identity and target reference rather than a bare success flag.
- `launch`: requires both `launch_config_digest` and explicit security projection fields such as privilege, network mode, mounts, devices, capabilities, and key identity bindings.
- `docktap-runtime`: requires explicit workload/launch/instance identity where applicable plus explicit operation outcomes.

### Conditional identity requirements are explicit
`workload_id` is always required for workload-scoped launch verification. `instance_id` is conditionally required once a container-scoped operation has produced or referenced a concrete container instance.

Rationale:
- Requiring `instance_id` before container creation would incorrectly fail launch attempts that abort before an instance exists.
- Failing to require `instance_id` once container-scoped activity exists would make runtime attribution too loose for audit.

### No legacy compatibility downgrade rules in v1
The design assumes forward-looking profile enforcement only.

Rationale:
- The project is still in active development and not yet bound by production historical data guarantees.
- Avoiding legacy downgrade logic keeps the first contract crisp and testable.

## Risks / Trade-offs

- [Profile contract too weak for audit] -> Mitigation: require explicit hard-fail fields for object identity, launch boundary, and security-relevant launch configuration rather than accepting raw command logs as sufficient evidence.
- [Profile contract too strict for current producers] -> Mitigation: stage the work so contract freezing happens first, producer alignment second, and verifier enforcement third.
- [Reusing `launch_id` becomes constraining if one request later spans multiple attempts] -> Mitigation: state the v1 assumption explicitly in the contract so a later change can deliberately evolve the identity model if the runtime semantics change.
- [Docktap cannot naturally know the launch boundary] -> Mitigation: require explicit propagation of `launch_id` into launch-related runtime events instead of relying on workload-only grouping heuristics.
- [Verifier output becomes noisy] -> Mitigation: keep profile verdict states small and explicit (`verified`, `warning`, `incomplete`, `failed`) and separate profile findings from structural replay findings.

## Migration Plan

1. Freeze the profile contract in specs, including the `launch_id` decision and per-profile required fields.
2. Update REST producers to emit the required fields for `build`, `publish`, and `launch` flows.
3. Update Docktap runtime producers to emit the required identity and outcome fields for runtime verification.
4. Extend `tc-verify` to evaluate profile-specific rules and render profile-scoped verdicts in text and JSON output.
5. Add focused tests for producer payload shape and verifier profile evaluation.

Rollback strategy:
- Because the project is pre-production, rollback is simply reverting to the previous non-profile-aware verifier and producer payload behavior if the contract proves too strict during development.

## Open Questions

- Should Docktap carry `launch_id` only for launch-attributed `create` and `start` flows, or also propagate it into later `stop` and `rm` events for the same instance?
- Should `launch_config_digest` cover the full environment value set, or should environment variables be split into a digest plus a redacted key projection to reduce sensitive-value exposure?
- Should `publish` remain intentionally minimal in v1, or should signature/attestation verification outcomes become hard-fail requirements once the producer payloads are aligned?