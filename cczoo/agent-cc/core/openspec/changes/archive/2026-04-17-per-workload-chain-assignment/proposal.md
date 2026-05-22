## Why

Docktap currently submits all Docker lifecycle events to a hardcoded `chain_id="default"`, regardless of which workload the container belongs to. This means unrelated containers share a single trust chain, making workload-level audit and verification impossible. Per-workload chain assignment is the prerequisite for the Workload/Instance Mapping Model (GAP-03) and is the next step on the critical path after GAP-01 (Docktap → TruCon emission, completed).

## What Changes

- Docktap extracts the `io.trucon.workload-id` label from `docker create` request bodies and uses its value as the `chain_id` for that container's lifecycle events.
- A lightweight SQLite database persists the `container_id → workload_id` mapping so that subsequent operations (`start`, `stop`, `rm`) and Docktap restarts can resolve the correct chain.
- Containers without the label fall back to `chain_id="default"` (preserving current behavior).
- TruCon requires no changes — it already supports arbitrary `chain_id` values with independent sequence numbering and chain state.

## Capabilities

### New Capabilities
- `workload-chain-routing`: Docktap routes container lifecycle events to per-workload trust chains based on a container label, with SQLite-backed persistence for restart resilience.

### Modified Capabilities
- `docktap-trucon-commit`: The existing spec hardcodes `chain_id="default"` in scenarios. Scenarios must be updated to reflect dynamic chain_id resolution based on the `io.trucon.workload-id` label, with fallback to `"default"`.

## Impact

- **Code**: `docktap/proxy/docker_proxy.py` (label extraction from create body), `docktap/proxy/operation_log.py` (optional: workload_id field on OperationRecord), `docktap/trucon_client.py` (dynamic chain_id instead of hardcoded `"default"`), new `docktap/workload_store.py` (SQLite persistence).
- **Storage**: New SQLite file at `/dev/shm/docktap/container_map.db` (tmpfs, consistent with TruCon's ephemeral storage strategy).
- **APIs**: No REST API changes. TruCon `/commit` already accepts arbitrary `chain_id`.
- **Tests**: New tests for label extraction, workload store persistence/recovery, chain routing, and fallback. Updates to existing `docktap/tests/test_trucon_client.py` scenarios that assert `chain_id="default"`.
