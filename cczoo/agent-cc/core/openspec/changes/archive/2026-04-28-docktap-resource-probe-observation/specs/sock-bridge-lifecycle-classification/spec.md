## ADDED Requirements

### Requirement: Multi-resource probe requests SHALL use explicit observation types
Docktap SHALL classify high-frequency read-only resource probe requests in the network, volume, and plugin families as explicit observation types so they are distinguishable from generic fallback buckets.

#### Scenario: Network probe is classified explicitly
- **WHEN** `GET /networks/{id}` is processed
- **THEN** the request SHALL be classified as `network_inspect`

#### Scenario: Volume probe is classified explicitly
- **WHEN** `GET /volumes/{name}` is processed
- **THEN** the request SHALL be classified as `volume_inspect`

#### Scenario: Plugin probe is classified explicitly
- **WHEN** `GET /plugins/{name}/json` is processed
- **THEN** the request SHALL be classified as `plugin_inspect`

### Requirement: Existing inspect labels SHALL remain backward compatible
Docktap SHALL preserve existing image and container detail inspect labels while extending the probe taxonomy for additional resource families.

#### Scenario: Image inspect remains unchanged
- **WHEN** `GET /images/{name}/json` is processed
- **THEN** the request SHALL remain classified as `image_inspect`

#### Scenario: Container detail inspect remains unchanged
- **WHEN** `GET /containers/{id}/json` is processed
- **THEN** the request SHALL remain classified as `inspect`

### Requirement: Resource probe scope SHALL remain read-only in this change
Docktap SHALL limit this change to read-only probe paths and SHALL defer response outcome semantics and non-probe write paths to later changes.

#### Scenario: Resource probe classification does not imply miss semantics
- **WHEN** a network, volume, or plugin probe returns `404`
- **THEN** this change SHALL NOT redefine that response as `ok`, `miss`, or `error`
- **THEN** benign miss semantics SHALL remain deferred to a later change

#### Scenario: State-changing resource paths remain out of scope
- **WHEN** a non-read-only path in the same resource family is processed
- **THEN** this change SHALL NOT require a new observation label for that write path