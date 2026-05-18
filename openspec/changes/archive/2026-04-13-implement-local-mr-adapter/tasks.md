## 1. Adapter Interface Setup

- [x] 1.1 Create `LocalMRAdapter` abstract base class with methods to read and extend measurement registers.
- [x] 1.2 Document the required arguments and return types for the adapter methods.

## 2. TDX Implementation

- [x] 2.1 Create `TdxMRAdapter` class implementing the `LocalMRAdapter` interface.
- [x] 2.2 Implement the read property targeting the appropriate TDX sysfs nodes for measurement registers.
- [x] 2.3 Implement the extend operation interfacing directly with the TDX OS-level structures (or sysfs).
- [x] 2.4 Add exception handling for missing sysfs capabilities (e.g. running on non-TDX hardware).

## 3. Refactoring Api.py

- [x] 3.1 Update `TrustedLogAPI` parameter type to accept instances of `LocalMRAdapter`.
- [x] 3.2 Update register check logic in `TrustedLogAPI.submit` (or related methods) to use the new adapter rather than hardcoded boolean logic.
- [x] 3.3 Make sure existing tests pass using a mocked `LocalMRAdapter`.
- [x] 3.4 Optionally write a small integration test or sanity check test.