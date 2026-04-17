## 1. TruCon Auth Middleware

- [x] 1.1 Add `TRUCON_SERVICE_TOKEN` and `TRUCON_AUTH_DISABLED` to `src/tc_api/config.py` using `decouple.config`
- [x] 1.2 Implement Bearer token validation middleware in `src/tc_api/trucon/app.py` using FastAPI middleware: read token from `Authorization` header, compare with `hmac.compare_digest`, return 401 JSON on failure
- [x] 1.3 Add startup guard: if `TRUCON_AUTH_DISABLED` is not true and `TRUCON_SERVICE_TOKEN` is empty, log ERROR and exit
- [x] 1.4 Add startup warning log when `TRUCON_AUTH_DISABLED=true`

## 2. Client Credential Attachment

- [x] 2.1 Update `TrustedLogAPI._post_to_trucon()` in `src/tc_api/tlog_client.py` to attach `Authorization: Bearer <token>` header when `TRUCON_SERVICE_TOKEN` is set
- [x] 2.2 Update `TrustedLogAPI.get_commit_queue_status()` and other GET helpers in `src/tc_api/tlog_client.py` to attach the same header
- [x] 2.3 Update `TruConCommitter._post_to_trucon()` in `docktap/trucon_client.py` to attach `Authorization: Bearer <token>` header when `TRUCON_SERVICE_TOKEN` is set

## 3. Startup Script Token Generation

- [x] 3.1 Add token generation to `start.sh`: generate via `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` and export as `TRUCON_SERVICE_TOKEN`
- [x] 3.2 Add same token generation to `scripts/trust_service.sh` if it independently starts services

## 4. Test Infrastructure

- [x] 4.1 Set `TRUCON_AUTH_DISABLED=true` in `run_tests.sh` environment
- [x] 4.2 Write unit tests for the auth middleware: valid token, missing header, wrong scheme, invalid token, dev-mode bypass, startup guard
- [x] 4.3 Verify existing test suites pass with `TRUCON_AUTH_DISABLED=true`

## 5. Documentation

- [x] 5.1 Add Phase B upgrade path (mTLS / Unix socket credentials) note to `docs/overview_tasks.md` under a new task entry
- [x] 5.2 Update `docs/architecture.md` §9 to reflect the implemented Phase A auth mechanism and the deferred Phase B
