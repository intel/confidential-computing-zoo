## ADDED Requirements

### Requirement: CLI requires Event Log 0 for non-default chains
The chain verification CLI SHALL require every non-`default` chain to begin with Event Log 0 in both evidence-backed replay mode and live fallback mode.

#### Scenario: Evidence-backed verification of workload chain with baseline
- **WHEN** `tc-verify` replays a non-`default` chain from immutable-backend evidence and the first replayed record is Event Log 0
- **THEN** the CLI SHALL continue verification normally and SHALL evaluate replay, attested-head, and profile results on that chain

#### Scenario: Evidence-backed verification fails for workload chain without baseline
- **WHEN** `tc-verify` replays a non-`default` chain whose first replayed record is not Event Log 0
- **THEN** the CLI SHALL fail verification and SHALL report the missing baseline as a structural chain-origin error

#### Scenario: Live fallback verification also rejects missing baseline
- **WHEN** `tc-verify` runs in live fallback mode for a non-`default` chain whose first record is not Event Log 0
- **THEN** the CLI SHALL report the chain as failed rather than downgrading the issue to a warning or incomplete state