## ADDED Requirements

### Requirement: Non-default chains must begin with Event Log 0
`GET /verify-chain/{chain_id}` SHALL treat Event Log 0 as a structural prerequisite for every non-`default` chain. A non-`default` chain whose first record is not a baseline record SHALL be reported as invalid.

#### Scenario: Valid workload chain begins with baseline
- **WHEN** `GET /verify-chain/workload-a` is called and the first record in that chain is Event Log 0 followed by contiguous later records
- **THEN** the baseline-origin check SHALL pass and the chain's validity SHALL continue to depend on the remaining sequence, RTMR, and immutable-backend checks

#### Scenario: Workload chain missing baseline fails verification
- **WHEN** `GET /verify-chain/workload-a` is called and the first record in that non-`default` chain is a business or runtime event instead of Event Log 0
- **THEN** the response SHALL set `valid: false` and SHALL report the missing baseline as a structural verification error

#### Scenario: Pending baseline still satisfies origin requirement
- **WHEN** `GET /verify-chain/workload-a` is called and the first record is Event Log 0 but it is still pending immutable-backend confirmation
- **THEN** the chain SHALL satisfy the baseline-origin requirement even though the pending record still contributes to `rekor_pending`