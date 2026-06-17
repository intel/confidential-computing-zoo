## 1. System Refactoring

- [x] 1.1 In `trusted_container_log/local_mr.py`, modify `TdxMRAdapter.__init__` to accept the proper binary sysfs interface base path default (`/sys/class/misc/tdx_guest/measurements/rtmr`).
- [x] 1.2 In `trusted_container_log/local_mr.py`, modify `_get_val_path` and `_get_extend_path` inside `TdxMRAdapter` to match the exact pattern: `/sys/class/misc/tdx_guest/measurements/rtmr{index}:sha384` (noting read/write use the same path now).
- [x] 1.3 In `trusted_container_log/local_mr.py`, update `TdxMRAdapter.read()` to open the paths with `rb` (binary mode) and return `f.read().hex()` (encoding to hex for API conformance).
- [x] 1.4 In `trusted_container_log/local_mr.py`, update `TdxMRAdapter.extend()` to strip the `sha384:` prefix (if present), parse the string via `bytes.fromhex()`, validate the byte array length is == 48, and write it using `rb+` mode.

## 2. Test Remediation
- [x] 2.1 In `test_tlog_impl.py` or where applicable, adjust mock `TdxMRAdapter` invocations to simulate `rb+` filesystem behaviors and the returned `.hex()` formats.