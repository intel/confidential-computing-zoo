## Context

`tc-verify` currently treats live TruCon endpoints as first-class inputs: it uses `/chain-state/{chain_id}` to discover the current head, `/verify-chain/{chain_id}` to obtain local-chain diagnostics, and immutable-backend replay as a companion source. That implementation was acceptable for the first CLI release, but it no longer matches the repository's stated verification boundary, where remote operators should verify public Rekor history against an exported attested-head evidence package rather than against live TruCon state.

The repository already contains the producer-side evidence contract and export surface. `src/tc_api/trucon/evidence.py` defines the v1 evidence schema and binding helper, and `GET /evidence/{chain_id}` in TruCon exports evidence for the latest confirmed public head. What is still missing is the consumer-side contract in `tc-verify`: loading evidence as an input, deriving the replay target from that package, checking that replay reaches the attested head, and making the fallback nature of live TruCon verification explicit.

This change is cross-cutting because it touches CLI inputs and output shape, evidence validation, immutable replay flow, fallback semantics, and operator documentation.

## Goals / Non-Goals

**Goals:**
- Make evidence-backed verification the primary `tc-verify` execution path.
- Allow the CLI to consume a v1 attested-head evidence package without requiring live TruCon connectivity.
- Verify that immutable-backend replay reaches the chain head described by the evidence package.
- Separate immutable replay diagnostics from attested-head evidence diagnostics in both JSON and human-readable output.
- Preserve a transitional live TruCon mode for operators who still need in-CVM or tightly coupled workflows.

**Non-Goals:**
- Designing new producer-side evidence fields or changing the v1 attested-head evidence contract.
- Replacing Rekor replay with a different immutable-backend verification model.
- Implementing full remote TDX quote parsing and endorsement-chain validation beyond the current exported contract and producer-side strict export checks.
- Adding application-flow verification profiles for build, publish, launch, or docktap-runtime workflows.

## Decisions

### 1. Evidence package becomes the primary verifier input

`tc-verify` will support an evidence-backed invocation mode that loads a v1 attested-head evidence package from a user-supplied JSON source. In that mode, the CLI derives `chain_id`, `head_log_id`, `sequence_num`, and `mr_value` from the evidence package rather than from `/chain-state/{chain_id}`.

Rationale:
- This matches the architecture's intended remote-verifier boundary.
- It allows verification without live TruCon connectivity.
- It avoids treating a mutable control-plane API as the verifier's source of truth.

Alternatives considered:
- Keep live TruCon discovery as the default and make evidence optional. Rejected because it preserves the current trust-boundary mismatch.
- Replace `chain_id` entirely with evidence-only invocation. Rejected for now because it would make the migration more disruptive and remove a useful transitional path.

### 2. Live TruCon mode is retained but explicitly demoted to fallback

The existing live TruCon-assisted verification path remains available for transitional use, but CLI help text, docs, mode reporting, and result output will label it as fallback rather than as the preferred verifier contract.

Rationale:
- Existing users and tests can migrate incrementally.
- Some environments still rely on in-CVM access during the transition period.
- GAP-18C in `docs/overview_tasks.md` explicitly calls for fallback demotion rather than abrupt removal.

Alternatives considered:
- Remove live TruCon mode immediately. Rejected because the current repository and tests still use it.
- Keep live TruCon mode without any special labeling. Rejected because it keeps the architecture drift hidden.

### 3. Verification output is split into replay and attested-head result domains

The CLI result model will represent immutable replay and attested-head evidence as separate diagnostic domains. The normalized result will still provide one overall summary, but that summary will be derived from at least two explicit sub-results:
- immutable replay verdict
- attested-head evidence verdict

When live TruCon fallback is used, fallback diagnostics will remain explicit and separate rather than merged into the main evidence-backed result.

Rationale:
- Operators need to know whether a failure came from public replay, evidence mismatch, or fallback-only checks.
- This matches the architecture guidance that public replay and attested-head binding answer different questions.

Alternatives considered:
- Continue flattening all source findings into one mixed `sources` summary. Rejected because it hides the trust boundary and complicates operator interpretation.

### 4. v1 attested-head verification validates contract consistency and replay association, not full quote parsing

In this change, the consumer side will validate that the evidence package conforms to the shared v1 schema, that `report_data_binding.expected_value` is consistent with canonical recomputation from `chain_id`, `sequence_num`, `head_log_id`, and `mr_value`, and that immutable replay reaches the same attested head. The CLI will not introduce full independent parsing of the opaque TDX quote bytes in v1.

Rationale:
- The repository already enforces strict producer-side export checks in TruCon before returning evidence.
- No existing consumer-side quote parsing or endorsement verification library is present in the current codebase.
- This keeps the first external-evidence proposal implementable while still improving the trust boundary materially.

Alternatives considered:
- Require full remote quote verification in the same change. Rejected because it would expand scope significantly and is not supported by the current repository primitives.

### 5. Freshness handling remains strict only when the evidence says it should be

If `expires_at` is present in the evidence package, the CLI will treat expiry as a hard failure. If `expires_at` is absent, the CLI will not invent an implicit expiry window in v1; it will report the absence of an expiry bound in diagnostics instead.

Rationale:
- The current evidence contract makes `expires_at` optional.
- Inventing a hidden freshness policy in the CLI would create an untracked contract not present in the shared evidence schema.

Alternatives considered:
- Impose a default maximum age derived from `generated_at`. Rejected because no repository-wide policy has been chosen.

## Risks / Trade-offs

- [Consumer-side quote bytes are not independently parsed in v1] → Keep the limitation explicit in docs and output, and scope future quote-verification work as a follow-on change once a verifier-side library and policy are chosen.
- [CLI now has two execution modes] → Use explicit mode reporting and help text so operators can tell whether they ran evidence-backed verification or live TruCon fallback.
- [JSON output may need additive restructuring] → Preserve stable top-level summary fields where practical and add clearly named replay and attested-head sections instead of silently repurposing existing fields.
- [Evidence without `expires_at` can still be replayed indefinitely] → Surface missing-expiry as diagnostic context and defer hard freshness policy to a later contract change.

## Migration Plan

1. Add evidence-backed CLI input handling and shared evidence loading helpers.
2. Refactor result normalization so replay and attested-head findings are emitted separately.
3. Keep live TruCon mode available, but relabel it in help text, docs, and JSON/human-readable output as fallback.
4. Update CLI tests to cover evidence-backed success, evidence-to-chain mismatch, expired evidence, and fallback mode behavior.
5. Update verification docs and testing guidance to present evidence-backed verification as the preferred operator flow.

Rollback strategy:
- Because the change is centered on CLI behavior, rollback is limited to restoring the prior live TruCon-centric invocation path and result normalization. No runtime data migration is involved.

## Open Questions

- Which library or platform policy should eventually be used for independent verifier-side TDX quote validation?
- Should a future revision require `expires_at` for all exported evidence packages once operator freshness policy is standardized?