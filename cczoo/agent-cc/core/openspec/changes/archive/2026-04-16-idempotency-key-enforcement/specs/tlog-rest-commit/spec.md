## MODIFIED Requirements

### Requirement: tc_api performs DSSE signing locally
The tc_api commit handler SHALL construct the DSSE predicate (without `prev_log_id`), sign it using the caller's OIDC identity token via `sigstore-python` in offline mode, and send the resulting bundle to TruCon via `POST /commit`. The tc_api SHALL read the TruCon URL from the `TRUCON_URL` configuration variable. The `TrustedLogAPI` constructor SHALL accept a `trucon_url` parameter. Business endpoints SHALL pass the OIDC identity token string to `commit_record()` via the `commit_options={"identity_token": token_str}` parameter. The token SHALL be acquired by the calling endpoint using `Issuer.production().identity_token()`. The `commit_record()` method SHALL generate a random idempotency key (format: `idk-<12-hex-chars>`) and include it as `idempotency_key` in the `POST /commit` payload sent to TruCon. Callers MAY override the key via `commit_options={"idempotency_key": custom_key}`.

#### Scenario: tc_api signs and forwards to TruCon
- **WHEN** a business endpoint (build/publish/launch) calls `commit_record()` with an identity token in `commit_options`
- **THEN** `TrustedLogAPI` SHALL sign the DSSE envelope locally and POST the bundle to TruCon's `/commit` endpoint

#### Scenario: TruCon unavailable
- **WHEN** tc_api cannot reach TruCon at the configured `TRUCON_URL`
- **THEN** the commit SHALL raise `BackendSubmitError` with `retryable=True`, and the calling endpoint SHALL catch the error, log a warning, and continue the workflow with a degraded transparency status

#### Scenario: Idempotency key included in commit payload
- **WHEN** `commit_record()` posts to TruCon
- **THEN** the payload SHALL include an `idempotency_key` field with a randomly generated key, unless the caller provided one in `commit_options`
