## REMOVED Requirements

### Requirement: Non-default chains must begin with Event Log 0
**Reason**: The system no longer models non-default `chain_id` values as independently replayable RTMR-backed measured chains.
**Migration**: Use `chain_id="default"` for measured verification and use workload or instance metadata for non-cryptographic grouping.

## MODIFIED Requirements

### Requirement: Full chain traversal via GET /verify-chain
TruCon SHALL expose `GET /verify-chain` as a default-only measured-chain verification endpoint. The endpoint SHALL read all `commit_queue` records for `chain_id="default"`, ordered by `sequence_num`, and verify sequence continuity, RTMR chain integrity, and immutable-backend confirmation status for that single node-wide measured chain. The API SHALL NOT accept a caller-supplied measured `chain_id` selector.

#### Scenario: Verify the default measured chain
- **WHEN** a client calls `GET /verify-chain` and the default-chain records have contiguous sequence numbers, valid RTMR extends, and confirmed immutable-backend status where applicable
- **THEN** the response SHALL describe verification results for the node-wide default measured chain

#### Scenario: Parameterized verification route removed
- **WHEN** a client attempts to use the removed parameterized verification route from the multi-chain design
- **THEN** the API surface SHALL expose only `GET /verify-chain`, preventing callers from expressing non-default measured-chain semantics

#### Scenario: RTMR mismatch still invalidates default-chain verification
- **WHEN** a default-chain record's `mr_value` does not equal `SHA384(prev_mr_value || event_digest)`
- **THEN** that entry SHALL have `mr_ok: false`, the error SHALL describe the mismatch, and the top-level `valid` SHALL be `false`

