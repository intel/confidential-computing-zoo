## Why

The Trusted Log module provides a tamper-evident audit trail for container lifecycle events, binding remote immutable event history to local hardware runtime measurement registers (like TDX RTMR). We need to refactor the architecture to securely and effectively support Sigstore Transparent Log integration (Phase 1). The current synchronization and Identity Token lifecycle management must be adapted to avoid the "atomicity trap" during hardware state extension, and to safely decouple synchronous OIDC token usage from asynchronous network submission without facing token expiration.

## What Changes

- **Implement a SQLite-backed Commit Queue**: Use SQLite as a durable, local commit queue to replace the legacy `.sigstore.json` fallback, ensuring durability across process restarts. Write-Ahead Logging (WAL) logic will safely persist intentions before the hardware MR is extended.
- **Implement an In-Process Submission Daemon**: Create an asynchronous Submission Daemon running as a background thread inside the main FastAPI Web process to drain the SQLite Commit Queue.
- **Decouple Sigstore SDK Execution**: 
  - Restrict OIDC token usage to the synchronous `commit_record()` phase (main Web thread). This phase will use `sigstore-python` offline logic to exchange the OIDC token for a Fulcio Certificate, generate an In-Toto Statement wrapped in a DSSE (Dead Simple Signing Envelope), and save this fully-signed payload into the SQLite queue.
  - The Submission Daemon (`submit_record()`) asynchronously reads the statically-signed blob and explicitly pushes it to the Rekor API.
- **Remove On-chain Requirements**: Drop on-chain ledger implementations from the initial refactor focus.
- **Support In-Toto DSSE Envelopes**: Switch payload structure from simple JSON blobs to In-Toto/DSSE standards for universally verifiable supply chain artifacts.

## Capabilities

### New Capabilities
- `trusted-log-sqlite-queue`: Durable storage of committed and signed EventLogs pending remote publication to Rekor.
- `in-process-submission-daemon`: Multi-threaded asynchronous daemon inside FastAPI for remote Rekor submission handling retries.
- `sigstore-dsse-envelope`: Generation of In-Toto statements (wrapped in DSSE envelopes) synchronously exchanged with Fulcio prior to persistence.

### Modified Capabilities


## Impact

- `trusted_container_log/tlog_chain.py` and underlying persistence mechanisms will be refactored to support SQLite and asynchronous operations.
- `main.py` and `services.py` will need modifications to spawn and cleanly shut down the background Submission Daemon thread on app lifecycle events.
- Dependencies: Requires `sqlite3` driver changes, and adjusting usage of `sigstore-python` SDK to separate Fulcio interactions from Rekor transparency log pushes.