## 1. Contract Documentation

- [x] 1.1 Update trusted-log documentation to describe the v1 attested head evidence envelope, including required fields, optional fields, and Event Log 0 boundary rules
- [x] 1.2 Record the v1 quote-binding decision for `chain_id`, `sequence_num`, `head_log_id`, and `mr_value`, and document `report_data_binding` semantics

## 2. Shared Schema And Validation

- [x] 2.1 Add a shared attested head evidence schema or model definition that encodes the v1 required and optional fields without introducing an export transport
- [x] 2.2 Add validation logic for required envelope fields and `report_data_binding` completeness, including ordered `bound_fields` expectations

## 3. Fixtures And Tests

- [x] 3.1 Add valid and invalid attested head evidence fixtures that exercise the canonical JSON contract
- [x] 3.2 Add tests that accept valid fixtures, reject missing required fields, and reject incomplete quote-binding metadata