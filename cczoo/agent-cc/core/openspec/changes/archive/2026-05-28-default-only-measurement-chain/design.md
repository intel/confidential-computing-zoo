## Context

The current tc_api and Docktap architecture routes different workloads to different `chain_id` values and then records each chain's `mr_value` as if that value were the result of replaying only that chain's history. In reality, TruCon extends one physical RTMR[2] for all admitted commits. That means the current verifier assumption,

`mr_n = SHA384(prev_mr || event_digest)`

is only sound if every RTMR-extending event belongs to the same logical measured chain. Once non-default traffic is admitted, per-chain replay no longer matches the physical register and the node becomes vulnerable to poisoning and verification failure.

## Goals / Non-Goals

**Goals:**
- Make the measured-chain model match the single physical RTMR reality.
- Eliminate cross-chain RTMR poisoning by removing independent non-default measured chains.
- Preserve workload and instance metadata for audit, observability, and runtime-policy queries.
- Make verification and evidence semantics explicit enough that operators cannot mistake metadata partitions for cryptographic isolation.

**Non-Goals:**
- Preserve per-workload or per-tenant cryptographic chain isolation on current TDX RTMR hardware.
- Provide automatic trust continuity for already-poisoned multi-chain history.
- Hide the breaking change behind silent server-side aliasing of arbitrary `chain_id` values.

## Decisions

### 1. Admit exactly one measured chain

TruCon will treat `default` as the only chain ID that is allowed to create or advance RTMR-backed chain state. Any API that implies independent measured-chain semantics will reject non-default chain IDs rather than trying to preserve the old multi-chain contract.

Rejected alternatives:
- Keep per-workload chains and rely on the existing process lock. This serializes writes but does not solve shared-register contamination.
- Silently coerce non-default `chain_id` values to `default`. This would break signed predicate semantics, hide a major contract change, and make evidence harder to interpret.
- Keep multiple logical chains and verify only software-linked history. That would no longer match the quote-backed `mr_value` contract.

### 2. Demote workload identity from chain boundary to metadata

Docktap and tc_api will continue to capture `workload_id`, `instance_id`, container identity, and related labels, but those fields will no longer choose a measured chain. They remain useful for workload-level filtering, profile evaluation, and operational correlation inside the single global measured chain.

### 3. Fail closed on non-default writes and replace parameterized measured reads

Non-default requests to baseline initialization, commit reservation, commit admission, and any other measured write path will return explicit errors. For read-only measured-chain surfaces, the old parameterized routes will be removed and replaced with default-only endpoints (`/chain-state`, `/verify-chain`, `/evidence`, `/confidential/evidence`, `/confidential/posture`) so callers cannot imply independent non-default RTMR histories.

### 4. Roll out with a fresh default-chain epoch

Existing deployments may already have a physical RTMR state that cannot be replayed from the current default chain head because past non-default commits were mixed into the register. Rollout therefore requires a fresh default-chain epoch: archive or snapshot the existing local state for diagnostics, initialize a new default Event Log 0 from the current platform baseline, and only then resume measured commits.

### 5. Keep historical non-default data as diagnostics, not as trusted measured history

Previously recorded non-default rows may still be useful for incident analysis or workload correlation, but they must not continue to appear as independently trustworthy measured chains. Verification and evidence surfaces will not endorse them as cryptographically replayable RTMR histories.

## Risks / Trade-offs

- [Breaking client behavior] -> Update tc_api and Docktap producers in the same rollout and return explicit server-side errors for stragglers.
- [Loss of per-workload chain UX] -> Preserve workload and instance metadata plus query surfaces so operators can still group events without implying RTMR isolation.
- [Migration burden on existing nodes] -> Publish a runbook for archiving old queue state and re-baselining the default chain before reenabling measured commits.
- [Operator confusion about old data] -> Document that pre-change non-default histories are diagnostic only and must not be used as attested RTMR chains.

## Migration Plan

1. Freeze producers that still emit non-default measured-chain commits.
2. Archive existing commit queue state and any exported evidence that operators may need for incident analysis.
3. Start a fresh default-chain epoch by reinitializing Event Log 0 from the current platform baseline.
4. Roll out tc_api and Docktap updates that always submit measured commits on `default` while retaining workload metadata in the signed payload.
5. Re-enable evidence export and verification only for the new default-chain epoch.

## Open Questions

- Whether workload and instance queries need additional fields once `chain_id` stops carrying workload identity.