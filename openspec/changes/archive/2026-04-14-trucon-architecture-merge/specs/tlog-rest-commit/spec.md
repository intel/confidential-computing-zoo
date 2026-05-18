## RENAMED Requirements

### Requirement: Commit endpoint accepts signed bundle
FROM: The Trust API SHALL expose a `POST /commit` endpoint
TO: TruCon SHALL expose a `POST /commit` endpoint

### Requirement: tc_api performs DSSE signing locally
FROM: send the resulting bundle to Trust API via `POST /commit`
TO: send the resulting bundle to TruCon via `POST /commit`

### Requirement: Chain status endpoint
FROM: The Trust API SHALL expose a `GET /chain-state/{chain_id}` endpoint
TO: TruCon SHALL expose a `GET /chain-state/{chain_id}` endpoint

### Requirement: Queue status endpoint
FROM: The Trust API SHALL expose a `GET /status` endpoint
TO: TruCon SHALL expose a `GET /status` endpoint

## MODIFIED Requirements

### Requirement: tc_api performs DSSE signing locally
The tc_api commit handler SHALL construct the DSSE predicate (without `prev_log_id`), sign it using the caller's OIDC identity token via `sigstore-python` in offline mode, and send the resulting bundle to TruCon via `POST /commit`. The tc_api SHALL read the TruCon URL from the `TRUCON_URL` configuration variable. The `TrustedLogAPI` constructor SHALL accept a `trucon_url` parameter.

#### Scenario: tc_api signs and forwards to TruCon
- **WHEN** a client sends a commit request to tc_api with an identity token
- **THEN** tc_api SHALL sign the DSSE envelope locally and POST the bundle to TruCon's `/commit` endpoint

#### Scenario: TruCon unavailable
- **WHEN** tc_api cannot reach TruCon at the configured `TRUCON_URL`
- **THEN** tc_api SHALL return HTTP 503 to the caller with an error indicating the sequencer is unavailable
