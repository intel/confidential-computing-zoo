## MODIFIED Requirements

### Requirement: Signing uses shared OIDC credentials
Docktap SHALL use the same OIDC credential acquisition mechanism as tc_api (`sigstore.oidc.detect_credential()`) to sign DSSE bundles. When a valid OIDC token is available, the token SHALL be used for Fulcio signing (existing behavior). When no OIDC token is available but a valid session delegation exists for the target chain, Docktap SHALL sign the DSSE bundle using the chain owner key and include `delegation_id` in the predicate. The DSSE predicate format, entry digest computation, and event digest computation SHALL be identical regardless of signing path.

#### Scenario: DSSE bundle format matches tc_api
- **WHEN** Docktap constructs a DSSE bundle for a Docker operation
- **THEN** the bundle uses predicate type `https://trusted-log.dev/v1`, two-level SHA-384 digest computation, and Sigstore offline signing — identical to tc_api's `TrustedLogAPI.commit_record()`

#### Scenario: Owner key signing when delegation active and no OIDC token
- **WHEN** Docktap constructs a DSSE bundle, no OIDC token is available, and a valid delegation exists for the target chain
- **THEN** Docktap SHALL sign the DSSE envelope using the chain owner key (ECDSA P-384 + SHA-256), include `delegation_id` in the predicate, and submit the signed intoto entry to Rekor with the owner public key PEM as verifier

#### Scenario: Predicate includes delegation_id when delegation-signed
- **WHEN** a Docker operation is signed via delegation (owner key path)
- **THEN** the DSSE predicate SHALL include a `delegation_id` field referencing the active delegation's identifier
