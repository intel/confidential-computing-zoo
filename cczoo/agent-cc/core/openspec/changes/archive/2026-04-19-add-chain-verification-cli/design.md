## Context

The repository already has two partial verification surfaces, but neither is a complete operator tool. `TrustedLogAPI.verify_record()` can query and replay immutable backend entries, while TruCon's `GET /verify-chain/{chain_id}` checks local chain continuity, RTMR linkage, and non-TEE `prev_log_id` fallback behavior. Business flows only use the much lighter `verify_chain_state()` health-style check. The result is an implemented verification plane without a stable package CLI or a stable output contract.

This change packages those existing verification surfaces into one explicit operator entry point. The user has already chosen the key scoping decisions: only `chain_id` is supported in v1, the CLI lives in the Python package rather than `scripts/`, immutable-backend replay is the primary verdict source, non-TEE verification is test-only, and the CLI must emit per-record detail plus a stable JSON schema.

## Goals / Non-Goals

**Goals:**
- Add a package-level CLI command for chain verification.
- Accept `chain_id` as the sole verification target in v1.
- Aggregate immutable-backend replay results and TruCon local verification into one normalized result.
- Provide a stable JSON result model plus concise human-readable terminal output.
- Support `--signer-identity`, `--expected-entry-count`, `--fail-on-pending`, and `--require-tee`.
- Make non-TEE results visibly test-only and fail when `--require-tee` is set.

**Non-Goals:**
- No workload-level, instance-level, record-level, or log-id-based CLI targeting in v1.
- No on-chain backend support changes.
- No redesign of TruCon's `/verify-chain/{chain_id}` semantics.
- No coupling to `FIX-03` (`SubmitResult`) or `FIX-05` (`SubmitStatus.OPEN`).
- No policy DSL beyond the explicitly supported CLI flags.

## Decisions

### 1. Package-level CLI entry point
The CLI will be exposed as a package console script rather than an ad hoc script under `scripts/`.

Rationale:
- This is an operator-facing product surface, not a one-off helper.
- The repository already publishes console scripts through `pyproject.toml`.
- Package placement gives the CLI access to shared config and verification code without duplicating bootstrap logic.

Alternative considered:
- A standalone `scripts/verify_chain.py` helper would be faster to prototype, but it would create a second-class interface with weaker discoverability and looser contract expectations.

### 2. `chain_id`-only target model in v1
The CLI will require a single `chain_id` argument and will not accept alternate selectors in the first version.

Rationale:
- It keeps argument semantics unambiguous.
- It matches the current TruCon verification endpoint shape.
- It prevents the proposal from expanding into workload/instance query design.

Alternative considered:
- Supporting `record_id`, `log_id`, `instance_id`, or `workload_id` now would blur the distinction between verification and exploration, and would require additional query contracts that do not exist yet.

### 3. Dual-source verification with immutable backend as primary source
The CLI will combine two sources:
- Immutable-backend replay verification for chain authenticity and replay validation.
- TruCon local chain verification for sequence, RTMR, and non-TEE fallback diagnostics.

The immutable-backend result is the primary source for the overall verdict, while TruCon contributes chain-local diagnostic detail.

Rationale:
- The immutable backend is the stronger audit evidence source.
- TruCon owns local chain state and measurement-specific checks, so its output remains necessary for detailed diagnostics.
- Combining both avoids forcing operators to manually correlate two tools.

Alternative considered:
- Treating TruCon as the primary verdict source would underweight immutable audit evidence.
- Treating immutable backend as the only source would lose local ordering and RTMR diagnostics.

### 4. CLI-owned stable result model
The CLI will define its own stable normalized result model instead of reusing one source response verbatim.

The normalized model will include:
- `target`: requested `chain_id`
- `mode`: TEE availability, effective verification mode, and whether TEE was required
- `summary`: overall success, status, counts, and first error location
- `sources`: immutable-backend result and TruCon result, each with source-local status
- `entries`: per-record normalized details
- `errors`: top-level execution or policy failures

Rationale:
- Source response shapes differ and will likely continue to differ.
- Operators need a stable JSON contract even if underlying APIs evolve.
- Human-readable output can be rendered from the same normalized structure.

Alternative considered:
- Returning raw source payloads would be easier initially but would make the CLI contract unstable and harder to consume in automation.

### 5. Explicit non-TEE classification
When verification runs without RTMR evidence, the CLI will classify the result as `non_tee_fallback` / test-only, not as production-equivalent TEE verification.

If `--require-tee` is passed and TEE evidence is unavailable, the CLI must fail.

Rationale:
- The repository already treats non-TEE mode as development/testing fallback rather than the primary trust model.
- This avoids presenting DB-level `prev_log_id` verification as equivalent to hardware-backed measurement proof.

Alternative considered:
- Treating non-TEE success as plain success would be simpler but would blur a security boundary the architecture currently documents.

### 6. Supported flags are policy inputs, not a general policy engine
The first version supports exactly four operator controls:
- `--signer-identity`
- `--expected-entry-count`
- `--fail-on-pending`
- `--require-tee`

Rationale:
- These controls cover the concrete operator checks already identified in exploration.
- Keeping the surface tight prevents the CLI from becoming a generic verification policy interpreter.

Alternative considered:
- A broader policy file or DSL would add design and testing complexity without a clear current need.

## Risks / Trade-offs

- **[Result divergence between sources]** → The CLI will preserve per-source status in `sources` and expose normalized per-entry details so mismatches are diagnosable instead of hidden.
- **[`verify_record()` currently returns summary-heavy output]** → This change extends immutable-backend verification contracts to produce richer structured detail for CLI consumption.
- **[Users may misread pending records as hard failures]** → Default output distinguishes `verified`, `incomplete`, and policy-driven failure; `--fail-on-pending` makes the stricter mode explicit.
- **[Users may misread non-TEE fallback as production-safe]** → The CLI will surface verification mode explicitly and fail fast when `--require-tee` is used.
- **[Future alternate target selectors may pressure the CLI interface]** → The design keeps `chain_id`-only targeting as a deliberate v1 limit so expansion can happen in a later change with separate requirements.

## Migration Plan

1. Add immutable-backend verification result enrichment needed by the CLI normalization layer.
2. Add a package CLI entry point and normalized result rendering.
3. Add automated tests for TEE, non-TEE fallback, pending handling, and policy flag behavior.
4. Document the CLI in operator-facing docs and testing docs.

Rollback is low-risk because this change adds a new operator surface rather than replacing an existing user-facing API path. If needed, the CLI entry point can be removed without changing the underlying TruCon verification endpoint semantics.

## Open Questions

- None for proposal readiness. The current proposal intentionally fixes the v1 scope and treats broader targeting and policy expansion as later work.