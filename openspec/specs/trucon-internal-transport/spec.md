## Purpose

Define the requirements for TruCon's same-machine internal transport and its compatibility posture during migration.

## Requirements

### Requirement: TruCon SHALL expose a same-machine Unix socket transport for internal callers
TruCon SHALL provide a Unix domain socket transport for tc_api and Docktap internal control-plane traffic. This transport SHALL be the steady-state internal path for same-machine deployments.

#### Scenario: Internal caller connects over Unix socket
- **WHEN** tc_api or Docktap sends an internal TruCon request in the same-machine deployment model
- **THEN** the request SHALL be sent over the configured shared Unix socket path

#### Scenario: Unix socket path is deployment-visible
- **WHEN** bare-metal or Compose deployment wiring is configured for TruCon
- **THEN** the socket path SHALL be placed in a directory shared with internal callers that need TruCon access

### Requirement: Internal clients SHALL prefer Unix socket transport over internal HTTP
tc_api and Docktap SHALL prefer the Unix socket transport for internal TruCon calls whenever the Phase B transport is enabled.

#### Scenario: tc_api uses Unix socket by default
- **WHEN** tc_api is configured for the Phase B internal transport
- **THEN** its internal TruCon client SHALL use the shared Unix socket path as the default request path

#### Scenario: Docktap uses Unix socket by default
- **WHEN** Docktap is configured for the Phase B internal transport
- **THEN** its internal TruCon client SHALL use the shared Unix socket path as the default request path

### Requirement: Compatibility HTTP support SHALL be transitional if retained
If TruCon retains HTTP + Bearer-token support during migration, that path SHALL be documented and treated as compatibility-only rather than the long-term same-machine transport contract.

#### Scenario: Compatibility path explicitly labeled
- **WHEN** documentation or configuration references the internal HTTP + Bearer-token path after Phase B support exists
- **THEN** that path SHALL be described as transitional compatibility rather than the preferred internal design

#### Scenario: Compatibility path does not redefine steady-state transport
- **WHEN** both Unix socket and HTTP internal paths exist during migration
- **THEN** the Unix socket path SHALL remain the preferred and default same-machine control-plane transport