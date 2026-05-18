## REMOVED Requirements

### Requirement: RTMR ordering proof
**Reason**: RTMR chain integrity verification moves to TruCon's `GET /verify-chain/{chain_id}` endpoint (see `trucon-chain-verification` spec). The Rekor-level verification in `TrustedLogAPI.verify_record()` no longer performs RTMR cross-checks directly — that responsibility belongs to TruCon which owns the chain state and `event_digest` data.
**Migration**: Use TruCon `GET /verify-chain/{chain_id}` for RTMR chain verification. Use `TrustedLogAPI.verify_record()` for Rekor-level entry lookup only.
