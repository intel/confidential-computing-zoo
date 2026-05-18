## 1. Fix RTMR Index

- [x] 1.1 Change `_local_mr.extend(0, ...)` to `_local_mr.extend(2, ...)` in `src/tc_api/trucon/app.py` commit path
- [x] 1.2 Update any `_local_mr.read(0)` calls to `_local_mr.read(2)`
- [x] 1.3 Add `RTMR_INDEX = 2` constant to TruCon module for single-source-of-truth
- [x] 1.4 Update existing tests that reference RTMR index 0 to use index 2

## 2. CCEL Digest Capability

- [x] 2.1 Create `src/tc_api/trucon/adapters/ccel.py` with `read_ccel_binary()` (reads `/sys/firmware/acpi/tables/CCEL`, returns bytes or None) and `compute_ccel_digest()` (returns `sha384:<hex>` or None)
- [x] 2.2 Write unit tests for CCEL reading (mock filesystem) and digest computation

## 3. TruCon `/init-chain` Endpoints

- [x] 3.1 Add Pydantic request/response models: `InitChainBaselineResponse(rtmr_value, ccel_digest, init_token)`, `InitChainRequest(chain_id, init_token, signed_bundle, pub_key)`, `InitChainResponse(record_id, sequence_num)`
- [x] 3.2 Implement `GET /init-chain/{chain_id}/baseline`: read RTMR[2] (no extend), compute CCEL digest, generate `init_token` (random nonce stored in memory), return 200 or 409 if chain exists
- [x] 3.3 Implement `POST /init-chain`: validate `init_token`, verify no existing `chain_state`, INSERT baseline record with `sequence_num=1` and `rtmr_extended=TRUE` (for submit daemon/crash recovery compat), initialize `chain_state`, return `record_id`
- [x] 3.4 Ensure `/init-chain` operations are serialized under `_sequencer_lock` to prevent races
- [x] 3.5 Write unit tests for both endpoints: success path, chain-exists (409), invalid token (400), token mismatch, token consumed, commit sequence, non-TEE mode (12 tests in test_init_chain.py)

## 4. TEE Keypair Generation and DSSE Signing in tc_api

- [x] 4.1 Add `init_chain(chain_id)` method to `TrustedLogAPI` in `src/tc_api/tlog_client.py`: call `GET /init-chain/{chain_id}/baseline`, generate ECDSA P-384 keypair, build Event Log 0 entries (baseline_rtmr, ccel_digest, pub_key PEM), sign DSSE envelope with TEE private key, call `POST /init-chain`, zero and discard private key
- [x] 4.2 Implement DSSE signing with ECDSA P-384 keypair (using `cryptography` library) inline in init_chain(), distinct from Sigstore signing path
- [ ] 4.3 Write unit tests for `init_chain()`: successful init, chain-exists skip (409 → no error), TruCon unreachable (warning logged, no crash), private key lifecycle

## 5. tc_api Lifespan Integration

- [x] 5.1 Add `init_chain("default")` call to `lifespan()` in `src/tc_api/main.py` after `TrustedLogAPI` creation, with try/except that logs warning on failure
- [x] 5.2 Handle multi-worker startup: 409 from `/init-chain` is silently skipped (returns None)
- [ ] 5.3 Write integration test: tc_api startup creates Event Log 0, subsequent commits get `sequence_num >= 2`

## 6. Regression and End-to-End Tests

- [ ] 6.1 Run full regression suite (`bash run_tests.sh`) and verify all existing tests pass with RTMR index fix
- [ ] 6.2 Write end-to-end test: init-chain → commit → verify submit daemon publishes Event Log 0 before subsequent records
- [ ] 6.3 Write test: Event Log 0 FAILED_TERMINAL blocks subsequent chain submissions
