## ADDED Requirements

### Requirement: Commit endpoint accepts signed bundle
The Trust API SHALL expose a `POST /commit` endpoint that accepts a JSON body containing `bundle` (the signed DSSE bundle as JSON string), `chain_id` (string), and `event_digest` (string). The endpoint SHALL return `record_id`, `sequence_num`, `mr_value`, and `prev_mr_value` on success.

#### Scenario: Successful commit
- **WHEN** tc_api sends a valid `POST /commit` with a signed bundle, chain_id, and event_digest
- **THEN** the Trust API SHALL return HTTP 200 with `record_id`, `sequence_num`, `mr_value`, and `prev_mr_value`

#### Scenario: Missing required fields
- **WHEN** tc_api sends a `POST /commit` without `bundle` or `chain_id`
- **THEN** the Trust API SHALL return HTTP 422 with a validation error

### Requirement: tc_api performs DSSE signing locally
The tc_api commit handler SHALL construct the DSSE predicate (without `prev_log_id`), sign it using the caller's OIDC identity token via `sigstore-python` in offline mode, and send the resulting bundle to Trust API via `POST /commit`.

#### Scenario: tc_api signs and forwards to Trust API
- **WHEN** a client sends a commit request to tc_api with an identity token
- **THEN** tc_api SHALL sign the DSSE envelope locally and POST the bundle to Trust API's `/commit` endpoint

#### Scenario: Trust API unavailable
- **WHEN** tc_api cannot reach the Trust API at the configured URL
- **THEN** tc_api SHALL return HTTP 503 to the caller with an error indicating the sequencer is unavailable

### Requirement: Chain status endpoint
The Trust API SHALL expose a `GET /chain-state/{chain_id}` endpoint returning the current chain state: `head_record_id`, `head_log_id`, `sequence_num`, `mr_value`, and `updated_at`.

#### Scenario: Query existing chain
- **WHEN** a client requests `GET /chain-state/{chain_id}` for an existing chain
- **THEN** the Trust API SHALL return HTTP 200 with the current chain state

#### Scenario: Query non-existent chain
- **WHEN** a client requests `GET /chain-state/{chain_id}` for a chain that has no records
- **THEN** the Trust API SHALL return HTTP 404

### Requirement: Queue status endpoint
The Trust API SHALL expose a `GET /status` endpoint returning `queued_count`, `failed_count`, and `next_sequence_num` for pending records.

#### Scenario: Query queue status
- **WHEN** a client requests `GET /status`
- **THEN** the Trust API SHALL return HTTP 200 with the current queue statistics
