## MODIFIED Requirements

### Requirement: Immutable-log backend adapters SHALL be isolated from service runtime code
Each immutable-log backend adapter SHALL live outside `tc_api` service runtime code and SHALL be organized as a backend module inside the standalone `tlog` distribution. Backend implementations SHALL depend on the `tlog` core contracts plus backend-specific libraries, while remaining separate from FastAPI orchestration and TruCon queue management.

#### Scenario: Rekor backend is isolated inside standalone tlog
- **WHEN** inspecting the Rekor backend implementation location
- **THEN** `SigstoreLogAdapter` SHALL live under the standalone `tlog` project rather than under `tc_api`

#### Scenario: On-chain backend scaffold is isolated inside standalone tlog
- **WHEN** inspecting the on-chain backend implementation location
- **THEN** `OnChainLogAdapter` SHALL live under the standalone `tlog` project rather than under `tc_api`

### Requirement: TruCon submit daemon SHALL load backend adapters at runtime
The TruCon submit daemon SHALL select and instantiate immutable backend adapters at runtime from validated startup configuration, using direct conditional imports rather than a plugin registry. When exactly one backend is configured, TruCon SHALL load that concrete adapter directly. When more than one backend is configured, TruCon SHALL load the configured backend adapters and wrap them in a composite immutable adapter that still satisfies the `ImmutableLogAdapter` contract.

#### Scenario: Default backend configuration resolves to Rekor
- **WHEN** TruCon starts without explicit backend configuration
- **THEN** the submit daemon SHALL load `SigstoreLogAdapter` from the consolidated `tlog.backends.rekor` namespace as the effective backend

#### Scenario: Single backend selection via environment variable
- **WHEN** the immutable backend configuration declares one supported backend such as `rekor` or `onchain`
- **THEN** TruCon SHALL load the corresponding adapter from the matching backend namespace inside `tlog`

#### Scenario: Multiple backends use a composite adapter
- **WHEN** the immutable backend configuration declares more than one supported backend
- **THEN** TruCon SHALL instantiate the corresponding backend adapters and wrap them in a composite immutable adapter before passing the adapter into the submit daemon

#### Scenario: Unknown backend raises clear error
- **WHEN** the immutable backend configuration contains an unsupported backend value
- **THEN** the submit daemon SHALL raise `ValueError` with a message listing supported backends

#### Scenario: Unsupported placeholder fanout is rejected
- **WHEN** the immutable backend configuration requests `rekor,onchain` while the on-chain adapter is still a placeholder implementation
- **THEN** TruCon SHALL fail startup with a clear configuration error rather than partially enabling fanout mode