## 1. Configuration Surface

- [x] 1.1 Replace the single immutable backend selector in `tc_api/trucon/config.py` with parsed write-set and primary/read backend configuration values.
- [x] 1.2 Define and document the phase-one write-policy configuration semantics for single-backend and future fanout modes.
- [x] 1.3 Add startup configuration validation helpers that reject unknown backend names and unsupported placeholder combinations such as `rekor,onchain`.

## 2. Composite Adapter Wiring

- [x] 2.1 Add a composite immutable adapter module under `tc_api/trucon/` that implements `ImmutableLogAdapter` and fans out `submit_bundle()` to configured backend adapters.
- [x] 2.2 Update TruCon immutable adapter loading in `tc_api/trucon/app.py` so single-backend configs return the concrete adapter and multi-backend configs return the composite adapter.
- [x] 2.3 Preserve primary-backend read behavior for `get_entry()`, `traverse()`, and `find_entries_by_payload_hash()` in the composite adapter skeleton.

## 3. Submit-Daemon Integration

- [x] 3.1 Update `tc_api/trucon/submit_daemon.py` so existing confirmation flow can operate against the composite adapter without changing current single-backend behavior.
- [x] 3.2 Surface secondary-backend submission outcomes through logging or structured metadata while keeping primary-backend confirmation authoritative in phase one.

## 4. Validation

- [x] 4.1 Add unit tests for config parsing and startup validation covering `rekor`, `onchain`, unknown backend names, and rejected `rekor,onchain` placeholder fanout.
- [x] 4.2 Add unit tests for composite adapter fanout behavior, including primary-backend return semantics and secondary-backend failure reporting.
- [x] 4.3 Run the focused TruCon and immutable-backend test slices needed to verify the new config surface and adapter wiring.