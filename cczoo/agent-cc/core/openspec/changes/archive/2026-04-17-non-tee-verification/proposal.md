## Why

In non-TEE environments (no TDX hardware), `verify-chain` currently degrades to checking only `sequence_num` continuity. The RTMR chain check is skipped because `mr_value` is NULL, leaving zero ordering integrity verification. Developers and CI systems cannot test that chain verification logic works correctly without TDX hardware. Additionally, TruCon's startup message for non-TEE mode is a quiet `logger.info()`, making it easy to miss that the system is running without hardware-backed ordering.

## What Changes

- `verify-chain` gains a `prev_log_id` linkage check as a fallback when `rtmr_available == False`. For each confirmed record, it verifies that `record[n].prev_log_id == record[n-1].log_id`. Unconfirmed records at the chain tail are reported as unverifiable (since `log_id` is only assigned on backend confirmation).
- TruCon startup warning is upgraded from `logger.info()` to `logger.warning()` with a clear banner indicating non-TEE mode is active and suitable for development/testing only.
- No changes to the signing flow, DSSE predicate format, or commit flow. `prev_log_id` remains excluded from the signed predicate.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `trucon-chain-verification`: Add `prev_log_id` linkage verification as fallback when RTMR is unavailable. Per-entry result gains `prev_log_id_ok` field.

## Impact

- **Code**: `src/tc_api/trucon/app.py` (verify-chain logic, startup warning)
- **API**: `GET /verify-chain/{chain_id}` response entries gain `prev_log_id_ok: bool | null` field (additive, non-breaking)
- **No new dependencies**
- **Tests**: New tests for prev_log_id verification fallback, startup warning level
