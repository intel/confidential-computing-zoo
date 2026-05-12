## MODIFIED Requirements

### Requirement: TdxMRAdapter mapping
The system MUST implement `TdxMRAdapter` to map local MR extensions to Intellectual TDX hardware registers using strictly `/sys/class/misc/tdx_guest/measurements/rtmr{index}:sha384` binary APIs.

#### Scenario: Extending a TDX measurement
- **WHEN** `extend` is called on a machine where Intel TDX hardware drivers are active
- **THEN** it converts input digests into 48-byte representations and writes them linearly into the RTMR memory buffer file without standard text encoding.