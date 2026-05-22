## Why

`main.py` and `services.py` still use the legacy `ChainedTransparencyLog` class for event collection, signing, and verification. This class operates on a completely separate code path from the `TrustedLogAPI` → TruCon sequencer pipeline that was designed to replace it. The result is two parallel trust-logging pathways — the old one signs directly via Sigstore and saves files locally, the new one performs DSSE signing, RTMR extend, and queues for asynchronous Rekor submission. Phase 1A migrates the business endpoints (build, publish, launch) to use `TrustedLogAPI` for commit, and replaces the legacy `save_transparencyLog` / `verify_transpaerncyLog` methods, eliminating the dual-path inconsistency.

## What Changes

- Replace all `ChainedTransparencyLog()` instantiations in `main.py` with the `TrustedLogAPI` instance already available at `app.state.trusted_log`.
- Convert scattered `tl_signer.add_entry({...})` calls into the structured `init_record → add_entry → commit_record` flow defined by `TrustedLogAPI`.
- Replace `services.py` method signatures that accept `ChainedTransparencyLog` with `TrustedLogAPI`.
- Replace `save_transparencyLog()` in `services.py` — signing is now handled inside `TrustedLogAPI.commit_record()`, audit file persistence is replaced by querying TruCon chain state after commit.
- Replace `verify_transpaerncyLog()` in `services.py` — chain-integrity verification queries TruCon's `GET /chain-state/{chain_id}` instead of re-loading a local backup file.
- Remove the `from .trusted_container_log import ChainedTransparencyLog` import from `main.py` and `services.py`.
- `tlog_chain.py` is **not deleted** in Phase 1A — deletion is deferred to Phase 1B after a verification endpoint is added to TruCon.

## Capabilities

### New Capabilities
- `tlog-commit-migration`: Migrate business endpoints from legacy `ChainedTransparencyLog` to `TrustedLogAPI.commit_record` flow.
- `tlog-audit-snapshot`: Post-commit audit file persistence using TruCon chain-state query instead of local chain export.

### Modified Capabilities
- `tlog-rest-commit`: `TrustedLogAPI.commit_record` must handle OIDC token passed from the caller (build/publish/launch endpoints acquire the token and pass it via `commit_options`).

## Impact

- **Code**: `src/tc_api/main.py` (6 endpoint functions), `src/tc_api/services.py` (`save_transparencyLog`, `verify_transpaerncyLog`, and 4+ methods with `tl_signer` parameter).
- **APIs**: No external API changes. Internal method signatures in `DockerService` change (parameter type `ChainedTransparencyLog` → `TrustedLogAPI`).
- **Dependencies**: No new dependencies. `tlog_chain.py` remains in-tree but unused by business code after migration.
- **Risk**: OIDC token acquisition timing — current code acquires the token late (after all `add_entry` calls); the new path needs it at `commit_record` time, which aligns with current timing.
