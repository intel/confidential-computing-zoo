## MODIFIED Requirements

### Requirement: TruCon exports attested head evidence through a read-only HTTP surface
TruCon SHALL expose a read-only HTTP endpoint at `GET /evidence` that returns a v1 attested-head evidence package only for the default measured chain. The endpoint SHALL always resolve the node-wide measured-chain identity as `default` and SHALL NOT accept a caller-supplied measured `chain_id` selector.

#### Scenario: Export default-chain head evidence
- **WHEN** a caller requests `GET /evidence` and the default chain has a confirmed public head
- **THEN** TruCon SHALL return a v1 attested-head evidence package associated with the latest confirmed default-chain head

#### Scenario: Parameterized evidence export removed
- **WHEN** a caller attempts to use the removed parameterized evidence route from the multi-chain design
- **THEN** the API surface SHALL expose only `GET /evidence`, preventing callers from expressing non-default measured-chain semantics

### Requirement: Evidence export is strict and confirmed-head only
TruCon SHALL export evidence only for the latest confirmed public head of the default measured chain.

#### Scenario: Default chain has no confirmed public head
- **WHEN** a caller requests `GET /evidence` and the default chain has no confirmed immutable-backend head yet
- **THEN** TruCon SHALL fail the export request rather than returning evidence for a pending local head

#### Scenario: Caller cannot choose an arbitrary historical or non-default head in v1
- **WHEN** a caller requests evidence export in v1
- **THEN** TruCon SHALL export only the latest confirmed public head for `chain_id="default"` and SHALL NOT support non-default or caller-selected historical head targets