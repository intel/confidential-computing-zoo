## 1. Export Surface

- [x] 1.1 Add a read-only TruCon HTTP endpoint that exports attested-head evidence for a chain
- [x] 1.2 Enforce latest-confirmed-public-head-only selection and fail export when no confirmed `head_log_id` exists

## 2. Evidence Assembly

- [x] 2.1 Integrate direct quote acquisition for TruCon evidence export using the local TDX configfs TSM path
- [x] 2.2 Compute `report_data_binding.expected_value` from canonical serialization of `chain_id`, `sequence_num`, `head_log_id`, and `mr_value`, then validate it against quote-backed report data

## 3. Validation And Documentation

- [x] 3.1 Add tests for successful export, missing confirmed head, quote acquisition failure, and binding mismatch failure cases
- [x] 3.2 Update trusted-log documentation to describe the strict HTTP export surface and confirmed-head-only behavior