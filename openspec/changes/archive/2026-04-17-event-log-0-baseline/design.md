## Context

The trusted-log chain records container lifecycle events as DSSE-signed, hash-linked entries submitted to immutable backends (Rekor). Each event extends RTMR[2] so that TDX attestation quotes can correlate remote event history with local TCB state. However, the chain currently starts from the first user-triggered event — there is no baseline record anchoring the chain to the platform's boot-time measurement state.

The architecture documents (`docs/trusted-log/architecture.md`, `docs/architecture.md`) define Event Log 0 as the mandatory chain anchor. Design decisions were confirmed during explore sessions on 2026-04-17 and recorded in `docs/overview_tasks.md` (GAP-05).

Current state:
- `src/tc_api/trucon/app.py`: `POST /commit` hardcodes `_local_mr.extend(0, ...)` — wrong RTMR index.
- `src/tc_api/trucon/adapters/tdx_mr.py`: Adapter is index-agnostic, but callers pass `0`.
- `src/tc_api/tlog_client.py`: No `init_chain()` method. No TEE-keypair signing path.
- `src/tc_api/main.py`: `lifespan()` creates `TrustedLogAPI` but performs no chain initialization.
- `EventLog.pub_key` exists in types but is always `None`.

## Goals / Non-Goals

**Goals:**
- Create Event Log 0 (baseline record) at tc_api startup, capturing RTMR[2] snapshot and CCEL digest.
- Embed a TEE-generated ECDSA P-384 public key in Event Log 0's `pub_key` field.
- Implement a two-phase `/init-chain` protocol on TruCon to support baseline record creation without RTMR extend.
- Fix RTMR index from `0` to `2` across all measurement operations.
- Keep chain initialization non-blocking: subsequent `/commit` calls queue normally while Event Log 0 is PENDING.

**Non-Goals:**
- AMD SEV-SNP or quote-only runtime support.
- Using the TEE keypair for signing subsequent events (α model: keypair is single-use for Event Log 0).
- Full CCEL binary storage (only SHA-384 digest is stored).
- Blocking tc_api startup until Event Log 0 is confirmed by Rekor.
- RTMR[0], RTMR[1], or RTMR[3] usage.

## Decisions

### D1: Two-phase `/init-chain` protocol (over single-endpoint or TruCon self-init)

**Choice**: tc_api calls TruCon via two HTTP requests: `GET /init-chain/{chain_id}/baseline` → `POST /init-chain`.

**Alternatives considered**:
- *Single `POST /init-chain` with TruCon generating the keypair and signing*: Breaks the architectural principle that tc_api signs, TruCon sequences. Would add signing responsibility to TruCon.
- *TruCon auto-initializes in its own `lifespan()`*: TruCon doesn't hold OIDC tokens or signing context. Event Log 0's DSSE needs a signer.

**Rationale**: Preserves the established pattern where tc_api handles all signing and TruCon handles sequencing/storage. The two-phase approach lets TruCon read platform state (RTMR[2], CCEL) atomically, while tc_api constructs and signs the DSSE envelope.

### D2: TEE-generated ECDSA P-384 keypair for Event Log 0 signing (α model)

**Choice**: tc_api generates an ECDSA P-384 keypair in memory, signs Event Log 0 with the private key, embeds the public key in `pub_key`, and discards the private key immediately after.

**Alternatives considered**:
- *Use Sigstore OIDC for Event Log 0 too*: No TEE-specific identity binding. The point of Event Log 0 is to anchor the chain to a key provably generated inside the TEE.
- *Keep keypair for all subsequent events (β model)*: Would require changing tc_api's entire signing flow. Sigstore transparency benefits lost.
- *TEE keypair + Sigstore counter-signature (γ model)*: Excessive complexity for v1.

**Rationale**: α model gives TEE identity anchoring for Event Log 0 with minimal disruption to the existing Sigstore signing path. Future phases can revisit if needed.

### D3: RTMR[2] only, hardcoded (over configurable index)

**Choice**: Fix RTMR index to `2` as a constant. No `RTMR_INDEX` env var.

**Alternatives considered**:
- *Configurable via `RTMR_INDEX` env var*: Over-engineering — RTMR[0]/[1] are firmware-locked, RTMR[3] is reserved. There is exactly one valid choice.

**Rationale**: RTMR[2] is the only register available to OS/application software in the TDX architecture. Making it configurable adds complexity without benefit.

### D4: CCEL digest only (over full binary or structured JSON)

**Choice**: Store `SHA384(raw_CCEL_binary)` in Event Log 0. Not the full binary, not parsed JSON.

**Alternatives considered**:
- *Full CCEL binary as base64*: Can be tens of KB. Bloats the DSSE predicate and Rekor entry.
- *Parsed structured JSON*: Requires a TCG event log parser. Significant implementation effort for marginal audit benefit.

**Rationale**: The digest proves the CCEL content was observed at init time. A verifier with access to the same CCEL (via TDX quote → CCEL retrieval) can independently hash and compare.

### D5: Non-blocking initialization (over blocking until confirmed)

**Choice**: Event Log 0 enters the commit queue as PENDING. Subsequent `/commit` calls proceed normally. The submit daemon's ordered submission (ascending `sequence_num`) guarantees Event Log 0 is published to Rekor before later records.

**Alternatives considered**:
- *Block tc_api startup until Event Log 0 is confirmed*: Would make tc_api availability dependent on Rekor reachability. Conflicts with the best-effort submission model.

**Rationale**: Existing ordered-submission semantics already guarantee correct publication order. Terminal failure of Event Log 0 blocks the entire chain (FAILED records block same-chain successors), which is the correct behavior — no trust anchor means no chain.

### D6: `init_token` for TOCTOU protection

**Choice**: Phase 1 (`GET /baseline`) returns an opaque `init_token` that Phase 2 (`POST /init-chain`) must present. TruCon validates the token to ensure the baseline snapshot hasn't been superseded.

**Rationale**: Without the token, a concurrent `/commit` between Phase 1 and Phase 2 could extend RTMR[2], making the baseline snapshot stale. The `init_token` lets TruCon detect and reject this race. In practice, this race is extremely unlikely during startup, but the protection is cheap to implement (a random nonce stored in memory).

## Risks / Trade-offs

- **[Risk] CCEL ACPI table may not exist on all TDX platforms** → Mitigation: CCEL read is best-effort. If `/sys/firmware/acpi/tables/CCEL` is absent, `ccel_digest` is null. Event Log 0 is still created with RTMR[2] baseline and pub_key.
- **[Risk] Multi-worker race on `init_chain()`** → Mitigation: First worker to call `POST /init-chain` succeeds; subsequent workers get HTTP 409 (chain exists) and skip. The `init_token` mechanism prevents partial-state corruption.
- **[Risk] Private key exists in memory briefly** → Mitigation: Key is generated, used for one signature, and immediately dereferenced. Python's GC will collect it. For defense in depth, explicitly zero the private key bytes before dereferencing (using `cryptography` library's key serialization).
- **[Risk] RTMR index change breaks existing test chains** → Mitigation: Existing test data in `builds/` was generated without real TDX hardware (non-TEE mode). No RTMR values were actually extended. The index change is safe.
- **[Trade-off] Two HTTP calls for init vs one** → Accepted: The extra round-trip happens exactly once per CVM lifetime. Architectural consistency outweighs the marginal latency.
