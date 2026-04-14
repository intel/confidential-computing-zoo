## Context

Currently, the `TrustedLogAPI` takes a `local_mr=None` argument upon initialization. If truthy, the system assumes there's a local Measurement Register available and proceeds to attempt extensions during log submission. However, this logic is a stub. It never actually queries or modifies the real OS-level Trust Service Module (TSM) through sysfs (like the TDX RTMRs). To provide hardware-rooted trust, we need a concrete implementation that bridges the `TrustedLogAPI` layer with the physical or virtualized TDX Measurement Registers.

## Goals / Non-Goals

**Goals:**
- Define a strict interface `LocalMRAdapter` that ensures separation of concerns.
- Implement `TdxMRAdapter` representing the specific TDX TSM sysfs extensions.
- Refactor `TrustedLogAPI` to utilize `LocalMRAdapter` instead of checking a generic boolean/none value.

**Non-Goals:**
- We will not implement adapters for other confidential computing architectures (e.g., AMD SEV-SNP) at this time, though the interface will allow them later.
- We will not rewrite the `TrustedLogAPI` beyond what is needed to ingest the `LocalMRAdapter` dependency.

## Decisions

- **Adapter Interface (`LocalMRAdapter`)**: Implement an abstract class for extending and fetching local Measurement Registers. This provides the blueprint.
- **TDX Implementation (`TdxMRAdapter`)**: Given Linux TSM and TDX semantics, we will read and write to sysfs (e.g., `/sys/kernel/tsm/rtmr*/...`) directly from Python, or shell out to a lightweight command if sysfs logic requires extra privileges or specific tools. Since the Python process needs permission, we'll document those requirements but code it assuming proper access.
- **Dependency Injection**: Pass the instantiated `LocalMRAdapter` object to `TrustedLogAPI` instead of a plain dummy value for `local_mr`.

## Risks / Trade-offs

- **Risk**: Linux TSM Sysfs paths may change or require strict root access.
  - *Mitigation*: Ensure the adapter correctly handles `PermissionError` and `FileNotFoundError` gracefully, indicating why it failed to the `TrustedLogAPI`.
- **Risk**: Integrating TDX logic may complicate local unit testing.
  - *Mitigation*: Provide a `MockMRAdapter` or default no-op behavior to let tests proceed without TDX hardware.