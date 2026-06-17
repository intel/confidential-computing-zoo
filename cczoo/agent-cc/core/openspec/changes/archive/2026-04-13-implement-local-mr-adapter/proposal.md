## Why

Currently, `TrustedLogAPI` initializes with simply `local_mr=None`, and during register extension it only checks `if self.local_mr:` to conditionally mock a measurement register. However, it lacks genuine integration with the OS-level TSM (Trust Service Module) or Sysfs required to read and write hardware TDX Measurement Registers (TdxMR). This missing `LocalMRAdapter` causes the system to be a mock-only pass-through lacking true hardware integration for trusted operations.

## What Changes

- Add a distinct `LocalMRAdapter` abstraction to manage Trusted Measurement Registers.
- Provide a concrete `TdxMRAdapter` implementation that securely queries the OS-level TSM (like sysfs files or device drivers) to get and extend real TDX Measurement Registers.
- Refactor `TrustedLogAPI` to inject and interact with a valid `LocalMRAdapter` rather than manually bypassing register changes via simple conditionals on `local_mr`.

## Capabilities

### New Capabilities
- `local-mr-adapter`: Introducing a well-defined Local Measurement Register interface with methods to get, read, and extend MRs on the host system.
- `tdx-mr-implementation`: Hardware-specific local MR adapter instance that connects to the TDX TSM layer/sysfs on the Linux OS.

### Modified Capabilities


## Impact

- `trusted_container_log/api.py`: Modifies how `local_mr` is consumed. It will now require an adapter interface to push measurements.
- Potential addition of new modules (e.g., `local_mr.py` or similar) to separate MR hardware communication logic from the transparent log API logic.