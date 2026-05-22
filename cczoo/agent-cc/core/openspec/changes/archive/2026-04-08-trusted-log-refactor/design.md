## Context

The Trusted Log module generates a tamper-evident audit trail linking local measurement registers (TDX RTMR) to remote supply chain transparency metrics. The legacy system relies on `.sigstore.json` for persistence and tightly couples the OIDC identity token generation with the Sigstore transparent log submission. Since OIDC tokens expire quickly, a network partition or heavy latency during the Sigstore push can crash the transaction out, causing a desynchronization (the "atomicity trap") between the permanently altered hardware state (RTMR) and the software-tracked transaction history. 

## Goals / Non-Goals

**Goals:**
- Eliminate the atomicity trap using a Write-Ahead-Log (WAL) style Commit Queue pattern before committing to the MR.
- Decouple OIDC token consumption from the asynchronous network submission process so retries don't encounter expired tokens.
- Adopt a globally standard In-Toto DSSE Envelope structure for transparent logging.
- Build an internally managed, background-threaded Submission Daemon that automatically recovers from network errors and publishes logs reliably.

**Non-Goals:**
- Implementing the "On-Chain Log" backend. Phase 1 focuses exclusively on Sigstore Transparent logs.
- Externalizing the daemon into a completely standalone system service (e.g., systemd service). It must remain an in-process FastAPI daemon thread.

## Decisions

1. **SQLite for the Local Commit Queue**
   * **Why**: The legacy system used file-backed `.sigstore.json` exports which are brittle under heavy concurrency and abrupt crashes. SQLite inherently offers ACID transactions and WAL mode, allowing the system to safely record intentions before the hardware MR is permanently extended.
   * **Discarded Alternatives**: Redis (adds networking overhead and infrastructure footprint), flat files (concurrency issues).

2. **In-Process Python Thread for Submission Daemon**
   * **Why**: By launching the daemon as a multithreaded background process within the FastAPI lifecycle, we avert the complexity of deploying and monitoring a separate OS-level daemon, while achieving the async queue-drain decoupling needed.
   * **Discarded Alternatives**: Celery/Redis background jobs; too heavy for this footprint.

3. **Pre-signing DSSE Envelopes (Offline Mode Sigstore)**
   * **Why**: To bypass OIDC token expiration, the main Web Thread API (`commit_record`) will execute the `sigstore-python` SDK in an "offline mode." It will exchange the token for a Fulcio Certificate, generate the signed In-Toto DSSE payload, and stop. This fully-validated static binary blob goes into SQLite. The background daemon (`submit_record`) picks up this static blob and invokes the lower-level Rekor clients to push it.
   * **Discarded Alternatives**: Raw JSON upload to Rekor (`hashedrekord` format) was discarded because it forces the verifier to fetch metadata from our private APIs instead of keeping the transparency log fully public and self-contained via In-Toto.

## Risks / Trade-offs

- **Risk: Thread Lifecycle / Fast API Shutdown**
  - If the FastAPI process shuts down abruptly (SIGKILL), the sqlite daemon thread might break mid-submission.
  - *Mitigation*: Tie the thread cleanly to the Starlette/FastAPI `lifespan` events. The queue state must update atomically ensuring duplicate uploads are squashed or safely idempotent in Rekor.

- **Risk: Sigstore SDK limitations**
  - The `sigstore-python` SDK is primarily designed as a cohesive sign-and-upload workflow. Exposing only the signing mechanics while deferring the push might require dropping down to lower-level sub-modules.
  - *Mitigation*: We will write specialized wrapper adapters around the SDK ensuring it adheres tightly to our sync/async divide.