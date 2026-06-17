## ADDED Requirements

### Requirement: Housekeeping activity SHALL use a documented interpretation contract
Docktap documentation SHALL define how daemon/internal housekeeping and post-runtime maintenance activity are interpreted in mixed Docker traces so they are not mistaken for primary workload lifecycle or secondary runtime behavior.

#### Scenario: Housekeeping remains distinct from workload runtime paths
- **WHEN** mixed-trace documentation explains housekeeping activity
- **THEN** it SHALL describe that activity as distinct from both primary workload lifecycle and secondary runtime exec flows

#### Scenario: Housekeeping interpretation is documentation-first
- **WHEN** housekeeping activity is documented
- **THEN** it SHALL be described as an operator-facing interpretation contract rather than as a parser or ingestion specification

### Requirement: The first-wave housekeeping contract SHALL remain narrowly scoped
Docktap documentation SHALL scope the first-wave housekeeping contract around post-exec cleanup and similar post-runtime maintenance context rather than a broad maintenance taxonomy.

#### Scenario: Post-exec cleanup anchors the first wave
- **WHEN** the first-wave housekeeping contract is documented
- **THEN** it SHALL use post-exec cleanup evidence such as `clean 2 unused exec commands` as a representative housekeeping anchor

#### Scenario: Broader maintenance families remain extension room
- **WHEN** the documentation references image GC, background scanning, or retry or reconcile loops
- **THEN** it SHALL treat them as future extension room rather than as fully specified first-wave housekeeping behavior

### Requirement: Housekeeping correlation SHALL allow contextual-first interpretation
Docktap documentation SHALL allow housekeeping activity to correlate to surrounding runtime activity primarily through local sequence context when strong object identifiers are unavailable.

#### Scenario: Contextual-first correlation is permitted
- **WHEN** housekeeping activity appears after nearby exec or runtime activity without stable object identifiers
- **THEN** the documentation SHALL allow local sequence order, timing proximity, and surrounding maintenance context to support interpretation

#### Scenario: Lack of stable identifiers does not invalidate housekeeping interpretation
- **WHEN** a housekeeping line does not expose explicit container or exec identity
- **THEN** the documentation SHALL allow that housekeeping activity to remain interpretable without requiring an object-precise join

### Requirement: Housekeeping guidance SHALL distinguish expected noise from investigation-worthy patterns
Docktap documentation SHALL define a minimal first-wave boundary between expected maintenance noise and housekeeping patterns worth later investigation.

#### Scenario: Limited post-runtime cleanup is treated as expected noise
- **WHEN** housekeeping activity appears as bounded cleanup after nearby runtime work
- **THEN** the documentation SHALL describe that pattern as expected maintenance noise rather than as a workload lifecycle failure

#### Scenario: Repeated or obscuring housekeeping is treated as investigation-worthy
- **WHEN** housekeeping activity becomes unusually repeated, delayed, or dense enough to obscure the surrounding runtime story
- **THEN** the documentation SHALL describe that pattern as worth later investigation

### Requirement: Daemon housekeeping SHALL remain separate from Docktap-local cleanup semantics
Docktap documentation SHALL state that daemon/internal housekeeping interpretation does not define Docktap-local retention, retry cleanup, or sidecar GC behavior.

#### Scenario: Sidecar-local cleanup remains out of scope
- **WHEN** the housekeeping contract is documented
- **THEN** it SHALL state that Docktap-local cleanup helpers and retry-retention behavior remain outside this contract

#### Scenario: Parser and automation concerns remain deferred
- **WHEN** the housekeeping contract references future anomaly handling or broader maintenance automation
- **THEN** it SHALL state that parser implementation, machine scoring, and operational automation remain future work