## 1. Model Update

- [x] 1.1 Add `prev_log_id_ok: bool | None` field to `ChainEntryResult` in `app.py`, defaulting to `None`

## 2. Startup Warning

- [x] 2.1 Upgrade TDX-not-found log from `logger.info()` to `logger.warning()` with "NON-TEE MODE" banner text in `app.py`

## 3. verify-chain prev_log_id Verification

- [x] 3.1 In `verify_chain()`, after fetching records, build prev_log_id linkage check gated on `rtmr_available == False`
- [x] 3.2 For each confirmed record, compare `prev_log_id` to preceding confirmed record's `log_id`; set `prev_log_id_ok` accordingly
- [x] 3.3 First record with `prev_log_id == None` gets `prev_log_id_ok = True`; unconfirmed records get `prev_log_id_ok = None`
- [x] 3.4 On mismatch, set `prev_log_id_ok = False`, populate `error`, and set top-level `valid = False`

## 4. Tests

- [x] 4.1 Add unit test: valid prev_log_id chain in non-TEE mode returns all `prev_log_id_ok: True`
- [x] 4.2 Add unit test: prev_log_id mismatch returns `prev_log_id_ok: False` and `valid: False`
- [x] 4.3 Add unit test: unconfirmed record returns `prev_log_id_ok: None`
- [x] 4.4 Add unit test: when `rtmr_available == True`, all entries have `prev_log_id_ok: None`
- [x] 4.5 Add unit test: startup warning emits WARNING-level "NON-TEE MODE" when TDX sysfs absent
