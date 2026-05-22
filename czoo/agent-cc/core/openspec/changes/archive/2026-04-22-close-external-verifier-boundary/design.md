## Context

The repository already supports the preferred verification story: exported attested-head evidence supplies the current-head binding, while immutable Rekor replay supplies historical continuity and Event Log 0 baseline origin. However, `tc-verify` still accepts a bare `chain_id` and performs live TruCon lookups as a normal CLI entry path. That leaves the external verifier contract ambiguous because an operator can still rely on internal control-plane APIs without making an explicit troubleshooting choice.

This change is cross-cutting because it affects CLI UX, normalized result semantics, migration guidance, and the distinction between internal operational APIs and the external verifier contract.

## Goals / Non-Goals

**Goals:**
- Make evidence-backed verification the only supported external operator workflow.
- Keep live TruCon-backed verification available, if retained, only as an explicit troubleshooting mode rather than an implicit fallback.
- Make CLI help text, JSON output, and human-readable output reflect the boundary between external verification and internal diagnostics.
- Preserve enough local diagnostic capability for tightly coupled deployments and incident response.

**Non-Goals:**
- Redesign the replay protocol, predecessor proof, or Event Log 0 contract.
- Change the attested-head evidence payload format unless a narrow compatibility gap is discovered during implementation.
- Remove internal TruCon APIs such as `/chain-state` or `/verify-chain`; this change only reclassifies how operator tooling uses them.
- Solve `GAP-07`, deployment hardening, mTLS, cross-node transport, or broader environment concerns.

## Decisions

### Decision: External verification is evidence-first and evidence-required
The operator-facing CLI contract will treat exported attested-head evidence as the required primary input for external verification. A bare `chain_id` will no longer imply a supported external verifier path.

Why:
- The architecture and verification docs already position evidence plus Rekor replay as the long-term boundary.
- This removes ambiguity about whether internal service state is part of the verifier contract.

Alternative considered:
- Keep the current implicit fallback and rely only on wording or warnings. Rejected because the CLI shape itself would still advertise two equivalent-looking entry paths.

### Decision: Retain live TruCon verification only behind an explicit troubleshooting switch
If live fallback remains in the CLI, it will require an explicit troubleshooting-mode flag rather than being selected implicitly by omission of evidence.

Why:
- Local diagnostics remain useful for pending-only chains, in-CVM debugging, and tightly coupled operational flows.
- An explicit flag preserves those uses while making the trust-boundary downgrade intentional and visible.

Alternative considered:
- Remove live fallback entirely from the CLI. Rejected for this proposal because it would also remove useful on-box diagnostics and increase migration risk without first separating troubleshooting from external verification.

### Decision: Result modeling must separate verifier outcomes from troubleshooting outcomes
Normalized output will keep evidence-backed external verification as the primary result model. When troubleshooting mode is explicitly used, the output must label that mode as internal or troubleshooting-only rather than presenting it as a peer verifier source.

Why:
- Today the fallback result shape still looks close to a normal verification result.
- The change should make the boundary obvious in both text and JSON consumers.

Alternative considered:
- Reuse the current fallback result model and only add stronger warning text. Rejected because downstream tooling could still misclassify fallback runs as supported external verification.

### Decision: No attested-head evidence schema expansion in this proposal
The proposal will not expand the evidence schema unless implementation reveals a concrete gap that prevents evidence-backed verification from standing alone as the operator path.

Why:
- The current open problem is contract clarity, not missing replay semantics.
- Pulling quote-field or payload-schema changes into this proposal would broaden scope and delay closure.

Alternative considered:
- Bundle evidence-schema refinements into this change. Rejected unless a blocking insufficiency is found.

## Risks / Trade-offs

- [Migration friction] → Operators who currently run `tc-verify <chain_id>` as a normal workflow will need a new flag or an evidence export step. Mitigation: provide explicit migration messaging in help text, docs, and error output.
- [Troubleshooting confusion] → Users may still misunderstand troubleshooting mode as production verification. Mitigation: mark the mode clearly in CLI help, output, and documentation as internal / troubleshooting-only.
- [Downstream JSON consumers break] → Existing automation may assume fallback sections or bare `chain_id` usage. Mitigation: preserve structured output where possible, but add versioned or explicit mode markers and document the contract change.
- [Scope creep into evidence design] → It is tempting to solve broader evidence questions here. Mitigation: keep this proposal focused on boundary closure and defer evidence-format changes unless a concrete blocker appears.

## Migration Plan

1. Update CLI argument parsing and help so evidence-backed verification is the default supported operator path.
2. Introduce an explicit troubleshooting flag for live TruCon-backed verification, or a comparably explicit internal-mode selector.
3. Update JSON and text output so troubleshooting runs are labeled as internal diagnostics rather than normal verifier results.
4. Update docs and examples to remove bare `chain_id` verification from recommended operator workflows.
5. Preserve rollback by keeping the underlying live TruCon verification code path available during the transition, gated behind the explicit troubleshooting selector.

## Open Questions

- Should the troubleshooting selector remain within `tc-verify` or move to a separate internal command in a later change?
- Do any downstream automation consumers rely on the current implicit bare-`chain_id` invocation pattern and need a compatibility window?
- Is one release of deprecation messaging sufficient before tightening the CLI entry contract further?