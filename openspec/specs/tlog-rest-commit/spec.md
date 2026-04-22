## Purpose

Define the requirements for REST-originated trusted-log commits emitted by tc_api, including signing behavior and the audit fields required by verification profiles.

## Requirements

### Requirement: tc_api performs DSSE signing locally
The tc_api commit handler SHALL construct replayable DSSE predicates only after obtaining a predecessor contract from TruCon. For replayable records, tc_api SHALL call the TruCon reservation endpoint first, SHALL receive `sequence_num`, `prev_event_digest`, `prev_lookup_hash`, and `intent_token`, SHALL construct the DSSE predicate with those values, SHALL sign it using the caller's OIDC identity token via `sigstore-python` in offline mode, and SHALL send the resulting bundle to TruCon `/commit` together with the `intent_token`. The tc_api SHALL read the TruCon URL from the `TRUCON_URL` configuration variable. The `TrustedLogAPI` constructor SHALL accept a `trucon_url` parameter. Business endpoints SHALL pass the OIDC identity token string to `commit_record()` via `commit_options={"identity_token": token_str}`. The token SHALL be acquired by the calling endpoint using `Issuer.production().identity_token()`. The `commit_record()` method SHALL generate a random idempotency key (format: `idk-<12-hex-chars>`) and SHALL reuse that same key across the reservation and final commit steps unless the caller overrides it via `commit_options={"idempotency_key": custom_key}`. The DSSE predicate SHALL include an `entry_digests` array containing per-entry SHA-384 digests alongside the raw `entries` array. The `digest` field SHALL be computed using the two-level algorithm: per-entry digests first, then event digest over `{event_id, event_type, created, entry_digests}`.

#### Scenario: tc_api reserves, signs, and commits through TruCon
- **WHEN** a business endpoint (build/publish/launch) calls `commit_record()` with an identity token in `commit_options`
- **THEN** `TrustedLogAPI` SHALL reserve a predecessor contract from TruCon, SHALL sign the DSSE envelope with the returned sequencing fields, and SHALL POST the signed bundle plus `intent_token` to TruCon `/commit`

#### Scenario: TruCon unavailable during reservation
- **WHEN** tc_api cannot reach TruCon at the configured `TRUCON_URL` during the reservation step
- **THEN** the commit SHALL raise `BackendSubmitError` with `retryable=True`, and the calling endpoint SHALL catch the error, log a warning, and continue the workflow with a degraded transparency status

#### Scenario: TruCon unavailable during final commit
- **WHEN** tc_api successfully reserves an intent and signs the bundle but cannot reach TruCon for the final `/commit`
- **THEN** the commit SHALL raise `BackendSubmitError` with `retryable=True` and the caller MAY retry the same logical operation using the same `idempotency_key`

#### Scenario: Idempotency key is shared by reserve and commit
- **WHEN** `commit_record()` performs the reservation-backed flow
- **THEN** the same `idempotency_key` SHALL be included in both the reservation request and the final `/commit` request payload

#### Scenario: Two-level digest in predicate
- **WHEN** `commit_record()` constructs the DSSE predicate
- **THEN** the predicate SHALL contain `entry_digests` computed per-entry and `digest` computed from `{event_id, event_type, created, entry_digests}` using the two-level SHA-384 algorithm

### Requirement: REST producers emit profile-aligned build and publish audit fields
REST-originated trusted-log commits for `build` and `publish` flows SHALL emit the minimum identity and outcome fields required by the verification profiles rather than relying on raw command logs alone.

#### Scenario: Build flow emits stable audit identities
- **WHEN** a build flow commits its trusted-log record
- **THEN** the emitted entries SHALL include `output_image_digest`, `dockerfile_digest`, `build_context_digest`, `base_image_digests`, and `build_status`

#### Scenario: Publish flow emits pushed subject identity
- **WHEN** a publish flow commits its trusted-log record
- **THEN** the emitted entries SHALL include `pushed_subject_digest`, `target_ref`, and `publish_status`

### Requirement: REST launch commits use `launch_id` as the attempt boundary
REST-originated launch commits SHALL emit the existing `launch_id` as the authoritative v1 launch-attempt identity and SHALL include workload-scoped launch audit data keyed to that identifier.

#### Scenario: Launch flow emits launch boundary
- **WHEN** a launch flow commits its trusted-log record
- **THEN** the emitted entries SHALL include `launch_id` and `workload_id`, and launch verification SHALL be able to treat that `launch_id` as the attempt boundary

#### Scenario: Launch failure before instance creation remains attributable
- **WHEN** a launch flow fails before any instance is created
- **THEN** the launch commit SHALL still contain `launch_id`, `workload_id`, and the failure outcome fields needed to audit that attempt without requiring `instance_id`

### Requirement: REST launch commits emit configuration digest and security projection
REST-originated launch commits SHALL emit both a stable launch configuration digest and explicit security-relevant launch fields.

#### Scenario: Launch flow emits required security projection
- **WHEN** a launch flow commits its trusted-log record
- **THEN** the emitted entries SHALL include `image_digest`, `launch_config_digest`, `privileged`, `network_mode`, `mounts`, `devices`, and `capabilities`

#### Scenario: Launch success emits resulting instance identity
- **WHEN** a launch flow successfully creates one or more container instances
- **THEN** the launch commit SHALL emit the resulting `instance_id` or instance identifier list associated with the same `launch_id`
