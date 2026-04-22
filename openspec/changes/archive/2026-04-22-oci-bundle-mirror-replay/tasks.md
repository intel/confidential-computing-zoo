## 1. Feasibility Spike

- [x] 1.1 Build an OCI mirror test harness that can publish and retrieve a replayable `bundle.json` end to end.
- [x] 1.2 Prove that `payload_hash` can drive stable mirror lookup without relying on `chain_id` or mutable tags as the primary key.
- [x] 1.3 Document and test verifier behavior for mirror-required and mirror-optional policy when mirrored content is missing or delayed.

## 2. Mirror Publication

- [x] 2.1 Add post-Rekor-confirmation mirror publication plumbing for newly written replayable bundles.
- [x] 2.2 Introduce a durable publish queue or equivalent retryable mechanism so mirror failures do not break Rekor confirmation.
- [x] 2.3 Attach secondary annotations or indexes needed for operations without making them the primary mirror lookup authority.

## 3. Mirror-Aware Verification

- [x] 3.1 Extend immutable replay verification to resolve mirrored bundles by `payload_hash` when public entry data cannot materialize replayable predecessor facts.
- [x] 3.2 Extend structured immutable-backend verification results to preserve public-only versus mirrored materialization provenance.
- [x] 3.3 Add unit and integration coverage for public-only replay, mirrored replay, and mirror-required failure paths without relying on cache-only reconstruction.

## 4. CLI and Profile Integration

- [x] 4.1 Extend CLI JSON and human-readable output to report `public-only`, `public+mirrored`, and `public+mirrored+attested` verification tiers.
- [x] 4.2 Add verifier policy or verification-profile inputs for mirror base configuration and mirror-required versus mirror-optional behavior.
- [x] 4.3 Update operator-facing documentation for mirror-backed replay verification, including the temporary public-only window before asynchronous mirror publication completes.