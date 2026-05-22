## 1. Spike: Intoto Entry + Raw Public Key Verification

- [x] 1.1 Extend demo to submit intoto v0.0.2 entry (instead of dsse) with owner key, verify attestation storage returns payload
- [x] 1.2 Confirm P-384 + SHA-256 works with intoto entry type on public Rekor

## 2. Delegation Storage

- [x] 2.1 Add `delegations` table to `/dev/shm` SQLite schema in `trucon/database.py` (columns: delegation_id, chain_id, scope JSON, expires_at, created_at, signer_identity, sequence_num)
- [x] 2.2 Add CRUD functions: `insert_delegation()`, `get_active_delegation(chain_id)`, `cleanup_expired_delegations()`
- [x] 2.3 Add tests for delegation storage lifecycle (insert, query, expiry)

## 3. Owner Key DSSE Signing

- [x] 3.1 Add `sign_dsse_with_owner_key(statement, private_key)` function in `sigstore_baseline.py` — builds PAE, signs with ECDSA P-384 + SHA-256, returns DSSE envelope dict
- [x] 3.2 Add `build_intoto_entry_from_owner_key(envelope, pub_key_pem)` function in `tlog-rekor/adapter.py` — constructs intoto v0.0.2 proposed entry with raw public key as publicKey
- [x] 3.3 Add `submit_owner_signed_entry(envelope, pub_key_pem)` function in `tlog-rekor/adapter.py` — POSTs intoto entry to Rekor, returns uuid/log_index/entry_dict
- [x] 3.4 Add unit tests for DSSE PAE construction, signing, and intoto entry building

## 4. Delegation Event Creation

- [x] 4.1 Add delegation predicate builder — constructs `event_type: "session.delegation"` predicate with delegation_id, scope, expires_at, chain_id, sequence_num, owner_authorization
- [x] 4.2 Add `POST /api/docktap/delegate` endpoint in `main.py` — consumes OIDC token, creates delegation chain event (Fulcio-signed), stores delegation in SQLite, returns delegation_id + expires_at
- [x] 4.3 Add tests for delegation endpoint (success, expired token, missing chain)

## 5. Submit Operation: Delegation Signing Path

- [x] 5.1 Modify `_resolve_identity_token_str()` in `trucon_client.py` to return a sentinel or secondary result indicating "no token but delegation available"
- [x] 5.2 Modify `submit_operation()` / `_do_submit()` to branch: if OIDC token → Fulcio path (existing); if delegation → owner key signing path (new)
- [x] 5.3 In owner key path: sign DSSE with owner key, build intoto entry, submit to Rekor, POST bundle to TruCon `/commit` — include `delegation_id` in predicate
- [x] 5.4 Add tests for submit_operation with delegation path (mock Rekor + TruCon)

## 6. Attestation Gate: Delegation-Aware

- [x] 6.1 Modify attestation gate in `docker_proxy.py` to check delegation validity (SQLite lookup) when `has_reusable_identity_token()` returns False
- [x] 6.2 Keep lifecycle grant as fallback after delegation check
- [x] 6.3 Add tests for attestation gate with delegation active, delegation expired, no delegation

## 7. TruCon Server: Delegation Admission

- [x] 7.1 Modify `/commit` endpoint in `trucon/app.py` to accept owner-key-signed bundles (no Fulcio cert) when delegation_id is present in predicate
- [x] 7.2 Add delegation validity check at admission: delegation exists, not expired, operation type in scope
- [x] 7.3 Add tests for TruCon admission with delegation (valid, expired, scope violation)

## 8. Verification: Delegation Annotation

- [x] 8.1 Add `_annotate_delegation_verification()` in `tlog_client.py` — parallel to `_annotate_owner_verification()`, annotates delegation_status on each event
- [x] 8.2 Modify `_extract_signer_identity()` to gracefully handle raw public key verifiers (return None instead of error)
- [x] 8.3 Modify `verify_record()` to call `_annotate_delegation_verification()` and adjust signer_identity_match logic for delegation-authorized events
- [x] 8.4 Add tests for delegation verification: proven, expired, scope_violation, missing

## 9. Integration Tests

- [x] 9.1 End-to-end test: OIDC login → create delegation → docker pull/create/start (owner key signed) → verify chain with delegation annotations
- [x] 9.2 Test: delegation TTL expiry → attestation gate blocks → re-login → new delegation → operations resume
