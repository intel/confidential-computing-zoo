## 1. Admission And Producer Changes

- [x] 1.1 Enforce `chain_id="default"` on TruCon measured-chain admission endpoints and return explicit errors for non-default requests.
- [x] 1.2 Update tc_api trusted-log flows to stop lazily initializing or reserving non-default measured chains.
- [x] 1.3 Update Docktap TruCon submission flows to always commit on `default` while preserving workload and instance metadata in the signed payload.

## 2. Verification And Evidence Semantics

- [x] 2.1 Restrict chain-state, verification, and attested-head evidence surfaces to the default measured chain and add clear operator-facing error responses.
- [x] 2.2 Adjust verification and evidence tests so they no longer assume independently replayable non-default RTMR chains.

## 3. Migration And Documentation

- [x] 3.1 Add rollout guidance for archiving old multi-chain state and starting a fresh default-chain epoch.
- [x] 3.2 Update architecture, API, and testing documentation to describe workload identity as metadata within one global measured chain.