## Why

The trusted-log chain currently has no baseline anchor. Every event is committed and extended into RTMR[2], but there is no "Event Log 0" that captures the platform's pre-existing measurement state at initialization time. Without this baseline record, verifiers cannot correlate the trust chain back to the CVM's boot-time integrity — the chain floats without a root. Additionally, the `pub_key` field on `EventLog` is always `None`, meaning no TEE-generated cryptographic identity is embedded in the chain. The RTMR index is also hardcoded to `0` instead of the correct `2` (OS/application layer register).

## What Changes

- Add a two-phase `POST /init-chain` protocol on TruCon that creates Event Log 0 without performing an RTMR extend — it captures the current RTMR[2] value and CCEL digest as baseline evidence.
- tc_api generates an ECDSA P-384 keypair in TEE memory at startup, signs Event Log 0 with the TEE private key (not Sigstore OIDC), and embeds the public key in the `pub_key` field.
- Add `init_chain()` method to `TrustedLogAPI` (`tlog_client.py`), called during tc_api's `lifespan()` startup.
- Fix RTMR index from hardcoded `0` to `2` across all extend/read operations.
- Add CCEL digest computation capability to TruCon (read raw CCEL from ACPI tables, compute SHA-384 digest).
- Initialization is a logical state — subsequent `/commit` calls are not blocked while Event Log 0 is PENDING.

## Capabilities

### New Capabilities
- `chain-initialization`: Two-phase `/init-chain` protocol on TruCon for creating Event Log 0 (baseline record) with RTMR[2] snapshot, CCEL digest, and TEE-generated public key.
- `ccel-digest`: Reading CCEL binary from ACPI tables and computing its SHA-384 digest for inclusion in Event Log 0.

### Modified Capabilities

## Impact

- **TruCon endpoints**: New `GET /init-chain/{chain_id}/baseline` and `POST /init-chain` endpoints in `src/tc_api/trucon/app.py`.
- **tc_api startup**: `src/tc_api/main.py` lifespan gains keypair generation and init-chain call.
- **tlog_client**: `src/tc_api/tlog_client.py` gains `init_chain()` method with TEE-keypair DSSE signing.
- **TdxMR adapter**: `src/tc_api/trucon/adapters/tdx_mr.py` — RTMR index fix from `0` to `2`.
- **TruCon commit path**: `src/tc_api/trucon/app.py` — RTMR index fix in `_local_mr.extend()` call.
- **Dependencies**: `cryptography` library for ECDSA P-384 keypair generation (already in environment via `sigstore`).
- **Tests**: New test file for chain initialization; existing tests updated for RTMR index change.
