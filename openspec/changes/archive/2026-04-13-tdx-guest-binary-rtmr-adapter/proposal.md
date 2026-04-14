## Why

The current `TdxMRAdapter` implementation attempts to write hex-encoded checksum strings directly to the Linux TSM sysfs paths (e.g., `/sys/kernel/tsm/rtmr0/extend`). However, in actual TDX environments, the standard hardware driver interface path is `/sys/class/misc/tdx_guest/measurements/rtmr{index}:sha384`, and crucially, it strictly requires raw 48-byte binary writes (`rb+`) rather than text-based hex strings. Failing to address this impedance mismatch means the trusted log cannot successfully measure into TDX RTMRs on supported guest kernels. Refactoring `TdxMRAdapter` to serve as a translation boundary (Anti-Corruption Layer) solves this by isolating the format conversions—keeping the higher-level API completely unaware of binary hardware quirks.

## What Changes

- Modify `TdxMRAdapter` in `trusted_container_log/local_mr.py` to hardcode the proper TDX Guest sysfs path: `/sys/class/misc/tdx_guest/measurements/rtmr{index}:sha384`.
- Change file I/O operations inside the adapter's `extend` method to use unbuffered binary mode (`rb+`).
- Translate incoming hex digest strings inside the `extend` method explicitly into 48-byte `bytes` arrays before issuing writes.
- Translate hardware binary responses back to hex strings for compatibility with the overarching `LocalMRAdapter` `extend` and `read` protocol signatures.

## Capabilities

### New Capabilities
- `tdx-guest-binary-rtmr`: Direct capability to extend RTMRs via the proprietary Intel TDX Guest class binary sysfs `/sys/class/misc/tdx_guest/measurements/rtmr` nodes.

### Modified Capabilities
- `implement-local-mr-adapter`: The underlying hardware behavior specification must document the required string $\leftrightarrow$ binary translation inside the adapter layer.

## Impact

- **Affected code**: `trusted_container_log/local_mr.py` (`TdxMRAdapter` class implementation), and potentially related unit tests.
- **Affected infrastructure/systems**: Only affects runtime operations when execution occurs alongside an actual Intel TDX hardware driver. No impact on generic mock configurations or Sigstore functionalities.