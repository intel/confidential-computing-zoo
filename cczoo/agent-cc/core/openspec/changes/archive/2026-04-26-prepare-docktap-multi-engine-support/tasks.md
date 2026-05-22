## 1. Runtime Engine Contract

- [x] 1.1 Introduce a normalized runtime-engine abstraction in Docktap that separates engine-specific request parsing from canonical lifecycle handling
- [x] 1.2 Update Docktap lifecycle metadata and logging paths to carry `runtime_engine` for every auditable runtime event
- [x] 1.3 Preserve the existing canonical lifecycle operations (`pull`, `create`, `start`, `stop`, `rm`) as the downstream contract across supported engines

## 2. TruCon Commit Path

- [x] 2.1 Update Docktap runtime commit payload construction to emit mandatory `runtime_engine` metadata on all auditable lifecycle events
- [x] 2.2 Keep Docker-backed commit behavior compatible with current chain routing, workload mapping, and launch attribution semantics while adding the new field
- [x] 2.3 Add or update unit tests for runtime commit entry generation and event payload expectations including `runtime_engine`

## 3. Runtime Verification Profile

- [x] 3.1 Update `docktap-runtime` profile evaluation to require `runtime_engine` on auditable runtime events
- [x] 3.2 Implement mixed-engine evaluation flow with shared core checks plus engine-aware rule dispatch keyed by `runtime_engine`
- [x] 3.3 Make missing `runtime_engine` fail the runtime profile and unknown-but-present values return `incomplete` with clear verifier diagnostics
- [x] 3.4 Add verification tests covering Docker baseline behavior, missing-engine failure, and unknown-engine incomplete outcomes

## 4. Documentation And Readiness

- [x] 4.1 Update Docktap architecture and API docs to describe the runtime-engine abstraction and stable canonical lifecycle model
- [x] 4.2 Update trusted-log verification docs to document `runtime_engine` requirements and mixed-engine profile semantics
- [x] 4.3 Record the canonical v1 engine identifiers and any normalization rules needed for future Podman onboarding
