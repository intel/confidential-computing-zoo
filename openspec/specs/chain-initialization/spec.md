## Purpose

Define the required initialization and baseline semantics for trusted-log chains, including explicit Event Log 0 creation and startup initialization behavior.
## Requirements
### Requirement: Lazy Event Log 0 creation for new non-default chains
TruCon SHALL create Event Log 0 automatically inside `POST /commit` when it receives the first commit for a previously unseen non-`default` `chain_id`. TruCon SHALL insert the baseline record before inserting the triggering business or runtime event.

#### Scenario: First workload-chain commit creates baseline and business event
- **WHEN** TruCon receives `POST /commit` for `chain_id="workload-a"` and no `chain_state` exists for that non-`default` chain
- **THEN** TruCon SHALL insert Event Log 0 with `sequence_num=1`, SHALL insert the triggering commit with `sequence_num=2`, and SHALL return the business commit result rather than a separate initialization response

#### Scenario: Default chain does not use lazy initialization path
- **WHEN** TruCon receives `POST /commit` for `chain_id="default"`
- **THEN** TruCon SHALL continue using the existing default-chain initialization semantics and SHALL NOT create an additional implicit baseline through the lazy workload-chain path

### Requirement: Concurrent first commits are serialized without caller-visible init races
When concurrent first commits target the same previously unseen non-`default` chain, TruCon SHALL serialize them under the sequencer lock so that exactly one baseline record is created and later callers observe a normal existing-chain commit path.

#### Scenario: REST and Docktap race on first workload commit
- **WHEN** one first commit for `chain_id="workload-a"` arrives from REST and another arrives concurrently from Docktap
- **THEN** the request that acquires the sequencer lock first SHALL create Event Log 0 and persist its own event, and the later request SHALL receive a normal successful commit response on the already-initialized chain instead of an initialization conflict

#### Scenario: Sequence numbers remain contiguous across first-commit race
- **WHEN** two first commits for the same new non-`default` chain are serialized by TruCon
- **THEN** Event Log 0 SHALL receive `sequence_num=1`, the first business event SHALL receive `sequence_num=2`, and the later business event SHALL receive `sequence_num=3`

### Requirement: Baseline creation failure rejects the triggering first business event
If TruCon cannot create the required Event Log 0 baseline for a new non-`default` chain, it SHALL reject the triggering first `/commit` and SHALL NOT persist a business or runtime event onto that chain without a baseline anchor.

#### Scenario: Baseline creation fails during first workload commit
- **WHEN** TruCon receives the first `POST /commit` for a new non-`default` chain and baseline creation fails before the triggering event is inserted
- **THEN** TruCon SHALL return an error for that commit and SHALL leave the chain without any persisted business or runtime records

### Requirement: Lazy-created workload baselines use existing Event Log 0 ordering semantics
Lazy-created workload-chain baselines SHALL reuse the existing Event Log 0 sequencing contract used by the `default` chain: the baseline record is the first record in the chain and later commits may proceed while the baseline remains pending immutable-backend confirmation.

#### Scenario: Subsequent workload commit while baseline is pending
- **WHEN** Event Log 0 for a workload chain has been inserted with `sequence_num=1` and remains `PENDING`
- **THEN** a later `POST /commit` on that same chain SHALL succeed normally with `sequence_num=3` or higher, and ordered submission SHALL still publish the baseline before later records

## ADDED Requirements

### Requirement: Baseline snapshot endpoint
TruCon SHALL expose `GET /init-chain/{chain_id}/baseline` that reads the current RTMR[2] value (without extending it) and computes the SHA-384 digest of the raw CCEL binary. The endpoint SHALL return `{rtmr_value, ccel_digest, init_token}`. If the chain already exists, the endpoint SHALL return HTTP 409.

#### Scenario: Successful baseline snapshot
- **WHEN** tc_api calls `GET /init-chain/{chain_id}/baseline` for a chain that does not yet exist
- **THEN** TruCon reads RTMR[2], computes CCEL digest, generates an opaque `init_token`, and returns `{rtmr_value, ccel_digest, init_token}` with HTTP 200

#### Scenario: Chain already exists
- **WHEN** tc_api calls `GET /init-chain/{chain_id}/baseline` for a chain that already has a `chain_state` entry
- **THEN** TruCon returns HTTP 409 with a descriptive error body

#### Scenario: Non-TEE environment
- **WHEN** TruCon is running without TDX hardware (no RTMR sysfs)
- **THEN** `rtmr_value` is null, `ccel_digest` is null, and the `init_token` is still generated

### Requirement: Chain initialization endpoint
TruCon SHALL expose `POST /init-chain` accepting `{chain_id, init_token, signed_bundle, pub_key}`. It SHALL verify the `init_token` is valid and that no chain_state exists for `chain_id`, then INSERT the baseline record with `sequence_num=1` and initialize `chain_state`. The RTMR SHALL NOT be extended for this record.

#### Scenario: Successful chain initialization
- **WHEN** tc_api calls `POST /init-chain` with a valid `init_token` and a signed DSSE bundle
- **THEN** TruCon inserts Event Log 0 into `commit_queue` with `sequence_num=1`, `rtmr_extended=FALSE`, and `status=PENDING`, initializes `chain_state` for the chain, and returns `{record_id, sequence_num}` with HTTP 200

#### Scenario: Invalid or expired init_token
- **WHEN** tc_api calls `POST /init-chain` with an invalid or already-used `init_token`
- **THEN** TruCon returns HTTP 400 with a descriptive error

#### Scenario: Concurrent init race
- **WHEN** two tc_api workers both call `POST /init-chain` for the same `chain_id`
- **THEN** the first call succeeds with HTTP 200, the second receives HTTP 409

### Requirement: Event Log 0 signed with TEE keypair
tc_api SHALL generate an ECDSA P-384 keypair in memory at startup, build Event Log 0 entries containing the baseline RTMR[2] value, CCEL digest, and the public key in PEM format, and sign the DSSE envelope with the TEE private key. The private key SHALL be discarded immediately after signing.

#### Scenario: TEE keypair signing
- **WHEN** tc_api constructs Event Log 0 during `lifespan()` startup
- **THEN** the DSSE envelope is signed with the ECDSA P-384 private key (not Sigstore OIDC), and the public key is included in the `pub_key` field of the Event Log 0 payload

#### Scenario: Private key lifecycle
- **WHEN** Event Log 0 has been signed and submitted via `POST /init-chain`
- **THEN** the private key bytes are zeroed and dereferenced; the private key is not stored or reused

### Requirement: Non-blocking initialization
Subsequent `POST /commit` calls SHALL NOT be blocked while Event Log 0 is still in PENDING state. The submit daemon's ordered-submission behavior (ascending `sequence_num`) SHALL guarantee that Event Log 0 is published to the immutable backend before any subsequent records.

#### Scenario: Commit while baseline pending
- **WHEN** tc_api calls `POST /commit` after `POST /init-chain` but before Event Log 0 is confirmed
- **THEN** the commit succeeds normally, the new record gets `sequence_num=2` (or higher), and the submit daemon publishes Event Log 0 first

#### Scenario: Baseline terminal failure blocks chain
- **WHEN** Event Log 0 reaches `FAILED_TERMINAL` status in the submit daemon
- **THEN** all subsequent records in the same chain are blocked from submission (existing FAILED-blocks-successors behavior)

### Requirement: RTMR index correction
All RTMR extend and read operations SHALL use index `2` (the OS/application-layer register). The hardcoded `index=0` in the TruCon commit path SHALL be corrected to `index=2`.

#### Scenario: Commit extends RTMR[2]
- **WHEN** TruCon processes a `POST /commit` request with TDX hardware available
- **THEN** `_local_mr.extend(2, event_digest)` is called (not index 0)

#### Scenario: Baseline reads RTMR[2]
- **WHEN** TruCon processes `GET /init-chain/{chain_id}/baseline` with TDX hardware available
- **THEN** `_local_mr.read(2)` is called to capture the current measurement value

### Requirement: tc_api lifespan chain initialization
tc_api SHALL call `init_chain()` during its `lifespan()` startup for the `"default"` chain. If the chain already exists (HTTP 409), the initialization SHALL be silently skipped. If TruCon is unreachable, a warning SHALL be logged and tc_api SHALL continue starting.

#### Scenario: First worker initializes chain
- **WHEN** the first tc_api worker starts and no default chain exists
- **THEN** `init_chain("default")` succeeds, Event Log 0 is created

#### Scenario: Subsequent workers skip initialization
- **WHEN** a second tc_api worker starts and the default chain already exists
- **THEN** `init_chain("default")` receives HTTP 409 and skips without error

#### Scenario: TruCon unreachable at startup
- **WHEN** tc_api starts but TruCon is not yet available
- **THEN** tc_api logs a warning and continues; chain initialization can be retried on first request
