## Context

The project has two coexisting trust-logging code paths:

1. **Legacy path** (`ChainedTransparencyLog` in `tlog_chain.py`): Used by `main.py` (build/publish/launch endpoints) and `services.py`. Collects key-value entries via `add_entry()`, signs them via `sign_pending_entries()` (direct Sigstore production signer → Rekor), saves bundles and chain state to local files, and verifies via `verify_chain()`.

2. **New path** (`TrustedLogAPI` in `api.py` → TruCon in `trucon.py`): Initialized in `main.py` lifespan as `app.state.trusted_log` but not yet wired to business endpoints. Performs DSSE signing with In-Toto statements, POSTs signed bundles to TruCon for sequenced RTMR extend + SQLite queue insert, with asynchronous Rekor submission via the embedded submit daemon.

The legacy path does not perform RTMR extends, does not use the TruCon sequencer, and does not benefit from the three-layer trust model (DSSE + RTMR + Rekor) defined in the architecture docs.

## Goals / Non-Goals

**Goals:**
- Wire business endpoints (build, publish, launch) to use `TrustedLogAPI` for event logging.
- Replace `save_transparencyLog()` with a commit through `TrustedLogAPI.commit_record()` plus a post-commit audit snapshot from TruCon chain state.
- Replace `verify_transpaerncyLog()` with a TruCon chain-state query (lightweight verification that the commit was sequenced).
- Remove all `ChainedTransparencyLog` usage from `main.py` and `services.py`.

**Non-Goals:**
- Full chain-traversal verification endpoint on TruCon (Phase 1B).
- Deleting `tlog_chain.py` from the source tree (Phase 1B).
- Restructuring the `trusted_container_log/` directory layout (Phase 2).
- Namespace separation of TruCon into its own package (Phase 3).

## Decisions

### 1. Accumulate entries on `TrustedLogAPI`, commit once per workflow

**Decision:** Each business endpoint (build, publish, launch) calls `init_record()` at the start of its async workflow, calls `add_entry()` at each step, and calls `commit_record()` once at the end (where `save_transparencyLog` currently is).

**Rationale:** This matches the existing cadence — entries are accumulated throughout the workflow and signed/submitted at the end. The `TrustedLogAPI` already supports this multi-step flow. Moving to per-step commits would be a larger behavioral change with no immediate benefit.

**Alternative considered:** Commit after every `add_entry()`. Rejected because it would produce many small Rekor entries per workflow, increasing latency and Rekor load without adding auditability (the entire workflow is the logical atomic unit).

### 2. Pass `TrustedLogAPI` instance from `app.state`, not reconstruct it

**Decision:** Business endpoints and `DockerService` methods receive the `TrustedLogAPI` instance via `app.state.trusted_log` instead of constructing a new object per request.

**Rationale:** `TrustedLogAPI` is stateless across requests (per-request state is in `_records`/`_entries` dicts keyed by `record_id`). A single instance is safe for concurrent use. This avoids re-initializing the Sigstore adapter on every request.

**Alternative considered:** Construct a new `TrustedLogAPI` per request. Rejected because it duplicates the `SigstoreLogAdapter` instantiation and the lifespan already creates a properly configured instance.

### 3. OIDC token passed via `commit_options` at commit time

**Decision:** The OIDC identity token is acquired in the endpoint function (as it is today) and passed to `commit_record()` via the `commit_options={"identity_token": token_str}` parameter.

**Rationale:** `TrustedLogAPI.commit_record()` already reads `commit_options.get("identity_token")` and constructs `IdentityToken(...)` from it. The current code already acquires the token late in the workflow (after all `add_entry` calls), so the timing aligns perfectly.

### 4. Audit snapshot replaces local chain export

**Decision:** After `commit_record()` returns a `CommitResult`, save the commit metadata (record_id, event_id, sequence_num, mr_value) as a JSON file to `builds/<id>/<type>-commit-receipt.json`. This replaces the three files the legacy path saved: `<type>-transparency.json`, `<type>-transparency_log-<idx>.sigstore.json`, and `<type>-chain.sigstore.json`.

**Rationale:** The canonical chain state is now owned by TruCon. Saving a local receipt provides the same auditability for debugging without duplicating chain management. The bundle itself is stored in TruCon's SQLite queue.

**Alternative considered:** Query TruCon chain-state endpoint after commit and save full chain. Rejected for Phase 1A as it adds latency and TruCon may not yet have confirmed the record (async submission).

### 5. Lightweight verification replaces full chain verify

**Decision:** Replace `verify_transpaerncyLog()` with a query to TruCon `GET /chain-state/{chain_id}` that checks the chain head matches the expected record. Full chain-traversal verification is deferred to Phase 1B.

**Rationale:** The legacy `verify_chain()` method verifies local file integrity and Sigstore signatures. In the new architecture, integrity is guaranteed by RTMR extends (hardware) and Rekor inclusion (transparent log). A chain-state head check confirms the commit was sequenced. Full verification requires a new TruCon endpoint that does not yet exist.

### 6. `DockerService` methods receive `TrustedLogAPI` instead of `ChainedTransparencyLog`

**Decision:** Change the `tl_signer` parameter type in `build_image()`, `generate_sbom()`, `encrypt_image()`, and other methods from `ChainedTransparencyLog` to `TrustedLogAPI`. The parameter name changes from `tl_signer` to `tlog` to reflect the new semantics.

**Rationale:** These methods only call `add_entry()` on the parameter. `TrustedLogAPI` does not expose a bare `add_entry()` — it requires a `record_id`. The calling endpoint will pass the `record_id` alongside the `TrustedLogAPI` instance, or the methods accept both and forward them.

**Implementation detail:** Since `TrustedLogAPI.add_entry(record_id, Entry(...))` takes `Entry(key, value)` dataclasses while the legacy `add_entry({dict})` takes plain dicts, each call site needs to convert `{"key": value_dict}` to `Entry(key="key", value=json.dumps(value_dict))`.

## Risks / Trade-offs

- **[Risk] Legacy file format change** → The three legacy output files per workflow (`-transparency.json`, `.sigstore.json`, `-chain.sigstore.json`) are replaced by a single `-commit-receipt.json`. Any downstream tools that read these files will break. **Mitigation:** Check for consumers of these files in scripts/ and tests/ before removing. Phase 1A can emit both old and new formats during a transition period if needed.

- **[Risk] TruCon must be running** → The legacy path was self-contained (no external service dependency). After migration, business endpoints require TruCon to be reachable. **Mitigation:** `TrustedLogAPI._post_to_trucon()` already raises `BackendSubmitError(retryable=True)` which the endpoint can catch and degrade gracefully (log warning, continue workflow, mark transparency log as pending).

- **[Risk] Entry format change** → Legacy `add_entry({dict})` vs new `add_entry(record_id, Entry(key, value))`. Bulk conversion of ~30 call sites. **Mitigation:** Mechanical transformation; each call is independent. No semantic changes, only structural.

- **[Trade-off] Verification downgrade in Phase 1A** → Full chain-integrity verification is replaced by a head-check. This is acceptable because RTMR and Rekor provide stronger integrity guarantees than the legacy local chain hash check, but the user-visible verification output will be less detailed until Phase 1B adds a proper verification endpoint.
