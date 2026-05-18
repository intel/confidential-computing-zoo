## Context

`introduce-trucon-event-orchestrator` is down to three unresolved items, but only two of them are actionable implementation gaps: REST control-plane compatibility coverage (`2.3`) and Docktap retry/ack handling (`3.2`). The current code already routes build, publish, and launch trust events through `TrustedLogAPI.commit_record()` into TruCon, and current Docktap code already signs and posts lifecycle events to TruCon after the Docker response is returned. What is missing is a narrower design that separates:

- verification work for control-plane compatibility from broad TruCon migration work
- reliability work for Docktap submission from the already-finished event contract work

This change is cross-cutting because it touches tc_api endpoint verification, Docktap runtime behavior, and test architecture across both `tests/` and `docktap/tests/`.

## Goals / Non-Goals

**Goals:**
- Define a focused integration-test target for build, publish, and launch flows under TruCon routing.
- Make the expected externally observable behavior explicit when TruCon succeeds and when commit submission degrades.
- Define a bounded, non-blocking retry model for Docktap submissions to TruCon.
- Define acknowledgement semantics tightly enough that implementation can proceed without redesigning the whole Docktap proxy.

**Non-Goals:**
- Reworking tc_api business workflows outside trust-event compatibility checks.
- Introducing synchronous confirmation from TruCon immutable backends into Docker CLI latency.
- Reopening the closed legacy write-path fallback decision.
- Designing a distributed delivery guarantee across multiple Docktap instances.

## Decisions

### D1: Treat REST compatibility as endpoint-level integration coverage, not a new API contract

The missing REST work is not a new service boundary; it is proof that the existing build, publish, and launch endpoints still expose their expected result/status fields after TruCon routing. The right scope is a focused integration test suite around those three flows, using controlled stubs for external tooling and TruCon commit behavior.

**Rationale:** the production code path is already migrated. The remaining risk is regression in endpoint-visible behavior, not missing core routing.

**Alternative considered:** define a new public compatibility endpoint or new response model. Rejected because the user-facing contract already exists.

### D2: Verify both success-path and degraded TruCon-path behavior for REST flows

Each of build, publish, and launch should be tested in two modes:

- TruCon commit succeeds and the workflow returns its normal success/result payload.
- TruCon commit fails or degrades in the commit path, while the business workflow still returns the expected status/result structure with degraded transparency state.

**Rationale:** the architecture explicitly allows business operations to continue when trust-event submission degrades. The missing coverage is precisely around this compatibility promise.

**Alternative considered:** only test the success path. Rejected because it misses the most failure-prone migration behavior.

### D3: Docktap retry stays local, bounded, and asynchronous

Docktap retry handling should use a local in-process retry mechanism that runs after the Docker response has already been returned. A failed `POST /commit` is stored as a retryable local submission item with bounded retry count and backoff. The immediate proxy result to the Docker CLI remains unaffected.

**Rationale:** this preserves the current non-blocking proxy contract while improving eventual delivery for transient TruCon failures.

**Alternative considered:** block Docker CLI until TruCon acknowledges. Rejected because it regresses latency and availability of the Docker control path.

### D4: Acknowledgement means TruCon accepted `/commit`, not immutable backend confirmation

For Docktap, “acknowledged” should mean an HTTP success response from TruCon `/commit` with a returned `record_id`/`sequence_num`, not later immutable-log confirmation. Once TruCon accepts the commit, responsibility transfers to TruCon's queue worker.

**Rationale:** immutable backend confirmation already belongs to TruCon's submission lifecycle. Requiring Docktap to wait for confirmation would collapse service boundaries.

**Alternative considered:** wait for confirmed `log_id` before considering the submission acknowledged. Rejected because it would make Docktap depend on backend latency and queue state.

### D5: Terminal Docktap failure remains observable but non-fatal to proxy behavior

If Docktap exhausts its bounded retries, the submission should be marked terminal in Docktap-local state and logged with enough context for operators and tests to observe the loss. This does not change Docker CLI success semantics.

**Rationale:** the proxy contract stays non-blocking, but silent loss is unacceptable.

**Alternative considered:** retry forever. Rejected because it creates unbounded memory/time growth and ambiguous operator state.

## Risks / Trade-offs

- [Risk] REST integration tests become brittle because build/publish/launch currently depend on many subprocess and environment interactions.  
  Mitigation: scope tests around stable endpoint-visible fields and stub external command/tool boundaries aggressively.

- [Risk] Docktap local retry state can grow if TruCon is unavailable for an extended period.  
  Mitigation: bounded retry count, explicit terminal failure state, and future linkage to retention/GC work.

- [Risk] Retry semantics may duplicate submissions if the original HTTP result is unknown.  
  Mitigation: preserve idempotency keys per queued Docktap submission so retries reuse the same logical commit intent.

- [Risk] Adding local retry machinery to Docktap may blur responsibility with TruCon's own retry worker.  
  Mitigation: keep Docktap retry responsibility strictly pre-ack; once TruCon accepts `/commit`, all downstream retry stays in TruCon.

## Migration Plan

1. Add delta requirements for REST compatibility coverage and Docktap retry acknowledgement semantics.
2. Implement REST integration tests first, because they validate existing migrated behavior without changing runtime logic.
3. Add Docktap local retry state, retry worker/timer behavior, and acknowledgement bookkeeping.
4. Add Docktap tests for transient failure recovery, acknowledgement completion, and terminal exhaustion.

Rollback strategy:
- REST compatibility test additions have no runtime rollback concerns.
- Docktap retry support should be introduced so that disabling the local retry path returns behavior to the current one-shot best-effort model without touching tc_api or TruCon contracts.

## Open Questions

- Should Docktap retry state live only in memory, or should it survive Docktap restart through a lightweight local store?
- What bounded retry policy is acceptable for v1: fixed attempts with linear backoff, or exponential backoff with a max ceiling?
- Do operators need an explicit health/inspection endpoint for pending Docktap retry items, or are structured logs sufficient for the initial rollout?