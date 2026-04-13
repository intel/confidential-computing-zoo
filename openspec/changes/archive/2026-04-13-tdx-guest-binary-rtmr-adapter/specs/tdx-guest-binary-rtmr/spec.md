## ADDED Requirements

### Requirement: Binary measurement extension via `tdx_guest`
The `TdxMRAdapter` implementation SHALL execute measurement extensions using unbuffered binary file writes to the Intel TDX Guest specific sysfs module paths, matching hardware constraints.

#### Scenario: Extending the RTMR with a valid hex string
- **WHEN** the adapter's `extend` method is invoked with a 96-character hex digest (or prefixed with `sha384:`)
- **THEN** it converts the string into exactly 48 raw bytes and securely writes it to `/sys/class/misc/tdx_guest/measurements/rtmr{index}:sha384` using `rb+` open hooks.

#### Scenario: Blocking an improperly sized string
- **WHEN** the adapter's `extend` method is invoked with a string forming a payload other than 48 bytes
- **THEN** it blocks the file system operation entirely and raises a `ValueError` prior to engaging the hardware.