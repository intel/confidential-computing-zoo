## ADDED Requirements

### Requirement: CCEL binary reading
TruCon SHALL read the raw CCEL binary from the ACPI tables path (`/sys/firmware/acpi/tables/CCEL`). If the file does not exist (non-TEE environment or platform without CCEL support), the CCEL data SHALL be treated as absent (null).

#### Scenario: CCEL available
- **WHEN** TruCon reads CCEL and `/sys/firmware/acpi/tables/CCEL` exists
- **THEN** the raw binary content is read successfully

#### Scenario: CCEL not available
- **WHEN** `/sys/firmware/acpi/tables/CCEL` does not exist
- **THEN** CCEL data is null and no error is raised

### Requirement: CCEL digest computation
TruCon SHALL compute the SHA-384 digest of the raw CCEL binary and return it as a hex string prefixed with `sha384:`. The digest SHALL be computed over the exact bytes read from the ACPI table without any transformation.

#### Scenario: Digest of available CCEL
- **WHEN** CCEL binary data is available
- **THEN** the digest is `sha384:<hex of SHA384(raw_bytes)>`

#### Scenario: Digest when CCEL absent
- **WHEN** CCEL binary data is null (file not found)
- **THEN** `ccel_digest` is null
