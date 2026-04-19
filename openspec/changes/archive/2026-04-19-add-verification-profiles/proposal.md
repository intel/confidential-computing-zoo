## Why

The project now has working chain replay, attested-head evidence export, and `tc-verify`, but it still lacks a frozen application-layer verification contract for the major flows the system claims to audit. Today operators can verify chain integrity and evidence association, yet they cannot deterministically answer whether a `build`, `publish`, `launch`, or Docktap runtime sequence contains the minimum security-relevant facts required for audit.

This change is needed now because the remaining verification work is blocked on contract clarity rather than infrastructure. Producer payloads and `tc-verify` behavior both need a shared profile definition before implementation can proceed without semantic drift.

## What Changes

- Introduce canonical verification profiles for `build`, `publish`, `launch`, and `docktap-runtime`, including required fields, hard-fail conditions, warning-only omissions, and profile-scoped verdict states.
- Define launch verification around the existing `launch_id` as the authoritative v1 launch-attempt boundary, rather than introducing a separate `launch_attempt_id`.
- Require producer-side trusted-log payload alignment so REST launch/build/publish events and Docktap runtime events emit the minimum fields needed by their verification profiles.
- Extend `tc-verify` from chain/evidence validation only to profile-aware verdict reporting, with separate profile outcomes instead of one synthesized workload verdict.
- Clarify how `workload_id`, `launch_id`, and `instance_id` interact in launch and runtime verification, including when `instance_id` is conditionally required.

## Capabilities

### New Capabilities
- `verification-profiles`: Defines the canonical audit contract for `build`, `publish`, `launch`, and `docktap-runtime` verification, including profile-specific field requirements, aggregation boundaries, and verdict semantics.

### Modified Capabilities
- `chain-verification-cli`: Extend `tc-verify` from structural replay/evidence reporting to profile-aware output and per-profile verdicts.
- `tlog-rest-commit`: Change REST-originated trusted-log payload requirements so `build`, `publish`, and `launch` commits emit profile-required audit fields.
- `docktap-trucon-commit`: Change Docktap commit payload requirements so runtime events emit the minimum profile-required identity and outcome fields for audit.

## Impact

- Affected code: `src/tc_api/services.py`, `src/tc_api/main.py`, `src/tc_api/cli/verify.py`, `docktap/trucon_client.py`, and supporting trusted-log verification helpers.
- Affected contracts: trusted-log event payload shape, launch evidence semantics, and CLI JSON/human-readable verification output.
- Affected systems: REST control plane, Docktap runtime interception, TruCon-backed event history, and operator verification workflows.
- No new external dependency is expected; the change primarily tightens contracts and propagates existing identifiers and audit data more consistently.