## 1. TruCon Unix Socket Transport

- [x] 1.1 Add TruCon configuration and listener support for a shared Unix domain socket path alongside the current single-instance startup model.
- [x] 1.2 Implement internal request handling over the Unix socket transport without changing commit/query semantics.
- [x] 1.3 Update tc_api's TruCon client to prefer the Unix socket transport for internal requests.
- [x] 1.4 Update Docktap's TruCon client to prefer the Unix socket transport for internal requests.
- [x] 1.5 Mark the existing HTTP + Bearer-token path as compatibility-only in code paths and configuration that remain during migration.

## 2. Caller Authentication And Policy

- [x] 2.1 Implement peer-credential-based caller authentication for Unix socket requests in TruCon.
- [x] 2.2 Derive and record a caller identity that distinguishes at least `tc_api` and `docktap` for authenticated internal requests.
- [x] 2.3 Add a minimal caller authorization matrix so tc_api retains full internal access and Docktap is restricted to commit-oriented endpoints by default.
- [x] 2.4 Preserve or adapt the development/test auth bypass so local test workflows remain explicit and observable.

## 3. Deployment Wiring And Verification

- [x] 3.1 Update bare-metal startup wiring (`start.sh` and related config) to create and share the TruCon socket path.
- [x] 3.2 Update Docker Compose wiring to share the TruCon socket directory across tc_api, TruCon, and Docktap.
- [x] 3.3 Add or update focused tests for Unix socket transport, peer-credential caller authentication, and caller-policy enforcement.
- [x] 3.4 Add migration and rollback notes for any temporary HTTP compatibility mode retained during rollout.

## 4. Contract Cleanup And Docs

- [x] 4.1 Resolve `FIX-03` by removing `SubmitResult` unless the implementation introduces a real record-inspection contract that requires it.
- [x] 4.2 Resolve `FIX-05` by removing `SubmitStatus.OPEN` unless the implementation also introduces a designed workflow that uses it.
- [x] 4.3 Update architecture and operational docs to describe the UDS-first internal transport, caller identity model, and any compatibility-window behavior.