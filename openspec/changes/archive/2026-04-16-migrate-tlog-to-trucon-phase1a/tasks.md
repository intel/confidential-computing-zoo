## 1. Update DockerService method signatures

- [x] 1.1 Change `build_image()` parameter from `tl_signer: ChainedTransparencyLog` to `tlog: TrustedLogAPI, record_id: str`
- [x] 1.2 Change `generate_sbom()` parameter from `tl_signer: ChainedTransparencyLog` to `tlog: TrustedLogAPI, record_id: str`
- [x] 1.3 Change `encrypt_image()` parameter from `tl_signer: ChainedTransparencyLog` to `tlog: TrustedLogAPI, record_id: str`
- [x] 1.4 Change remaining DockerService methods that accept `tl_signer` (sign_image, push_image, get_pubKey_from_KBS, etc.) to use `tlog: TrustedLogAPI, record_id: str`
- [x] 1.5 Convert all `tl_signer.add_entry({key: value_dict})` calls inside DockerService methods to `tlog.add_entry(record_id, Entry(key=key, value=json.dumps(value_dict)))`
- [x] 1.6 Remove `from .trusted_container_log import ChainedTransparencyLog` import from services.py

## 2. Replace save_transparencyLog and verify_transpaerncyLog

- [x] 2.1 Replace `save_transparencyLog()` with a new method that calls `tlog.commit_record(record_id, event_type, commit_options={"identity_token": token_str})` and saves the `CommitResult` as a JSON receipt file to `builds/<id>/<type>-commit-receipt.json`
- [x] 2.2 Replace `verify_transpaerncyLog()` with a new method that queries TruCon `GET /chain-state/{chain_id}` via `tlog.get_commit_queue_status()` or direct HTTP, checks the chain head, and returns a status string
- [x] 2.3 Remove the old `save_transparencyLog()` and `verify_transpaerncyLog()` methods from DockerService

## 3. Migrate main.py business endpoints

- [x] 3.1 In `build_package` endpoint: replace `tl_signer = ChainedTransparencyLog()` with `tlog = app.state.trusted_log; ctx = tlog.init_record()` and thread `record_id` through to `build_container_async`
- [x] 3.2 In `build_container_async`: convert all `tl_signer.add_entry()` calls to `tlog.add_entry(record_id, Entry(...))`, replace `save_transparencyLog` call with new commit+receipt method, replace `verify_transpaerncyLog` with new chain-state verification
- [x] 3.3 In publish endpoint and its async function: same migration as build — replace ChainedTransparencyLog with TrustedLogAPI flow
- [x] 3.4 In launch endpoint and `launch_container_async`: same migration as build
- [x] 3.5 In remaining endpoints (lunks, etc.) that use `ChainedTransparencyLog`: migrate to TrustedLogAPI flow
- [x] 3.6 Remove `from .trusted_container_log import ChainedTransparencyLog` import from main.py

## 4. Validation

- [x] 4.1 Verify no remaining references to `ChainedTransparencyLog` in main.py or services.py
- [x] 4.2 Run existing tests (`pytest tests/test_unit.py -v`) and fix any breakage from signature changes
- [x] 4.3 Manually verify a build/publish/launch flow produces the new commit-receipt.json format
