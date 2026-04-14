## 1. Request Forwarding Completeness

- [x] 1.1 Refactor request ingestion in `docktap/proxy/docker_proxy.py` to parse headers first and read full request body based on framing (`Content-Length` at minimum) before forwarding to Docker.
- [x] 1.2 Add defensive timeout/error handling for incomplete body reads so malformed clients fail fast without hanging worker threads.
- [x] 1.3 Add a regression test that sends a fragmented `POST /v*/containers/create` payload and verifies full body forwarding semantics.

## 2. Unified Operation Classification Contract

- [x] 2.1 Replace or adapt `_map_path_to_operation` usage so callback logging derives operation types from `get_operation_type` semantics.
- [x] 2.2 Normalize operation label vocabulary across all logging outputs (`create`, `rm`, `rmi`, etc.) and remove conflicting aliases (`run`, `remove`).
- [x] 2.3 Add a test/assertion path verifying callback and structured operation record emit the same operation type for identical requests.

## 3. Canonical Lifecycle Visibility

- [x] 3.1 Define and implement deterministic classification behavior for canonical preflight/image-inspect requests (`/_ping`, `/v*/info`, `/v*/images/<image>/json`).
- [x] 3.2 Update documentation in `docktap/architecture.md` if classification labels or wording change from current canonical sequence text.
- [x] 3.3 Add tests that assert preflight/image-inspect requests are not emitted as ambiguous `unknown` under normal lifecycle flow.

## 4. Streaming Detection Reliability

- [x] 4.1 Update `is_streaming_endpoint` matching in `docktap/proxy/operation_log.py` to reliably handle versioned wait/logs endpoint paths.
- [x] 4.2 Add regression tests for versioned wait/logs requests to validate streaming timeout policy selection.
- [x] 4.3 Verify no regressions in existing lifecycle/mixed/parallel suite behavior after streaming matcher changes.

## 5. Validation and Readiness

- [x] 5.1 Run targeted tests for new scenarios (fragmented body, classification consistency, streaming detection).
- [x] 5.2 Run full suite `python docktap/test_suite.py all` and relevant unit tests.
- [x] 5.3 Capture final implementation notes in change artifacts and confirm apply-ready status before archive workflow.
