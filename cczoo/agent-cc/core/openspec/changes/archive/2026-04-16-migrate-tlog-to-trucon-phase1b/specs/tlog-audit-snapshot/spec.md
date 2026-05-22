## REMOVED Requirements

### Requirement: Legacy transparency files no longer produced
**Reason**: Phase 1A already stopped producing these files. Phase 1B deletes the legacy code (`tlog_chain.py`, `verify_tlog()`, `/api/verify-tlog`) that could read them. This requirement is now enforced at the code level — the capability to produce or consume legacy files no longer exists.
**Migration**: All transparency data flows through TruCon commit receipts (`-commit-receipt.json`). Legacy `.sigstore.json` files are no longer readable by the system.
