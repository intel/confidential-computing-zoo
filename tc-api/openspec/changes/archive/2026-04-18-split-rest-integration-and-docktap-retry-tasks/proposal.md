## Why

The active `introduce-trucon-event-orchestrator` change is mostly implemented, but its remaining `2.3` and `3.2` tasks are still too broad to apply directly. We need a narrower change that turns those two gaps into executable work with clear behavioral requirements, so implementation can proceed without re-interpreting scope during coding.

## What Changes

- Define explicit public compatibility requirements for build, publish, and launch flows when trusted-event commits are routed through TruCon.
- Add focused integration coverage requirements proving those control-plane endpoints keep their expected response and status fields when TruCon is used or temporarily degraded.
- Replace Docktap's current one-shot best-effort commit behavior with a bounded transient retry and acknowledgement model that still does not block Docker CLI responses.
- Define the operational boundary between immediate proxy success, local retry responsibility, and terminal submission failure handling for Docktap.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `tlog-commit-migration`: tighten requirements so build, publish, and launch flows preserve their observable API/status behavior while their trust-event path runs through TruCon.
- `docktap-trucon-commit`: extend Docktap submission behavior from one-shot best-effort logging to bounded retry and acknowledgement semantics for transient TruCon failures.

## Impact

- Affected code:
  - `src/tc_api/main.py`
  - `src/tc_api/services.py`
  - `src/tc_api/tlog_client.py`
  - `docktap/trucon_client.py`
  - `docktap/main.py` or adjacent Docktap runtime support modules if local retry state is introduced
- Affected tests:
  - Control-plane integration coverage under `tests/`
  - Docktap reliability and retry coverage under `docktap/tests/`
- Affected behavior:
  - Public build/publish/launch result compatibility under TruCon routing becomes explicitly verified.
  - Docktap gains eventual-delivery handling for transient TruCon failures without regressing non-blocking proxy behavior.