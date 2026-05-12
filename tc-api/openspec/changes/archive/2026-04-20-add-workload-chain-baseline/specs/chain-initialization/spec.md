## ADDED Requirements

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