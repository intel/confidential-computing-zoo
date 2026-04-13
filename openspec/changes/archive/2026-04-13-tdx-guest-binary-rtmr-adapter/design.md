## Context

The `LocalMRAdapter` abstract interface maps internal system events to hardware Trusted Execution Environment (TEE) measurement extensions, specifically toward Intel TDX RTMRs via the `TdxMRAdapter` implementation. Currently, `TdxMRAdapter` uses string-based Linux TSM wrappers targeting `/sys/kernel/tsm/rtmr*/extend`. Real-world Linux kernels with TDX Guest drivers largely expose their proprietary interfaces under `/sys/class/misc/tdx_guest/measurements/rtmr{index}:sha384` where the inputs/outputs must be strictly 48-byte binaries rather than UTF-8 hex arrays. 

## Goals / Non-Goals

**Goals:**
- Target exactly the `tdx_guest` binary sysfs paths expected by unmodified TDX guest installations.
- Completely encapsulate binary/hex transformations inside the adapter—safeguarding the broader system string logic from hardware I/O specifics.
- Validate hex conversions securely to prevent under/over-sized digest extension payloads to the sensitive kernel module.

**Non-Goals:**
- Modify the `LocalMRAdapter` Python `Protocol` or `ABC` interface definitions in `trusted_log.types` or `api.py`. They remain securely operating in the Hex String domain.
- Create automated hardware probing/falling-back to TSM if the `tdx_guest` paths are missing. As explicitly instructed, this is a clean hardcoding substitution swap for a specific TDX guest model.

## Decisions

1. **Anti-Corruption Layer Pattern**: The abstraction boundary dictates `TdxMRAdapter` itself accepts strings (e.g., `"sha384:abcdef..."` or `"abcdef..."`) from the orchestrator and translates them.
2. **Binary Transformation**: `bytes.fromhex()` handles string-to-binary transformation (post-prefix stripping). Resulting binaries MUST be verified as exactly length 48 before the unsafe `open("...", "rb+")` operation.
3. **Hardcoded Paths**: Base path logic will rewrite `self._get_val_path` and `self._get_extend_path` functions to use `/sys/class/misc/tdx_guest/measurements/rtmr{index}:sha384` exactly for both `read` and `write` since it is a read-write mapped sysfs target.

## Risks / Trade-offs

- **[Risk]** Running this code on legacy platforms previously using the `tsm` generic interface will result in `FileNotFoundError`.
  - *Mitigation*: Emphasize to deployments that the agent natively relies strictly on the `.tdx_guest.` misc class drivers rather than newer abstract TSM layers.
- **[Risk]** Malformed sysfs structures locking the thread entirely on `open`.
  - *Mitigation*: Hardcode binary byte limits (`length=48`) validation in python prior to entering kernel space transitions.