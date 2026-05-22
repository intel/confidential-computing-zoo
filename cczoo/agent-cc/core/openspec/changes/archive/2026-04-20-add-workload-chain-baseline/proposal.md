## Why

Per-workload chains are now first-class verification targets, but only the startup-initialized `default` chain has an explicit Event Log 0 baseline today. New workload chains are created implicitly on first commit, which leaves chain-origin semantics inconsistent across chains and makes verification rules weaker for workload-scoped evidence than for the `default` chain.

## What Changes

- Extend chain initialization semantics so newly observed non-`default` workload chains receive an explicit Event Log 0 baseline before their first business or runtime event is accepted.
- Keep workload-chain baseline behavior aligned with the existing `default` chain model: Event Log 0 remains the baseline anchor, baseline submission stays non-blocking once the chain exists, and later records continue in normal sequence order.
- Make baseline creation lazy and internal to TruCon: the first `/commit` for an unknown non-`default` `chain_id` triggers baseline creation under the sequencer lock instead of requiring REST or Docktap to orchestrate a separate init flow.
- Reuse the current baseline fact model for workload chains, so multiple workload chains in the same CVM lifetime may record the same platform baseline facts while remaining distinct chains.
- Strengthen verification so both TruCon verification and `tc-verify` explicitly require non-`default` chains to start with Event Log 0 rather than treating workload chains without a baseline as structurally valid.
- Update architecture and verification documentation to describe lazy workload-chain baseline creation, first-commit sequencing, and the invariant that first-class workload chains must begin with Event Log 0.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chain-initialization`: expand Event Log 0 semantics from startup-only `default` chain initialization to lazy, race-safe baseline creation for newly observed non-`default` workload chains.
- `trucon-chain-verification`: require chain verification to treat a missing Event Log 0 on non-`default` chains as a structural failure rather than a tolerated alternate chain origin.
- `chain-verification-cli`: require `tc-verify` replay logic to explicitly fail non-`default` chains that do not begin with Event Log 0.

## Impact

- Affected systems: TruCon commit path, chain initialization flow, chain verification, and verifier replay rules.
- Affected code: `src/tc_api/trucon/app.py`, `src/tc_api/trucon/database.py`, `src/tc_api/tlog_client.py`, verifier support in `src/tc_api/cli/verify.py`, and related tests.
- Affected integrations: REST and Docktap keep their current `/commit` calling pattern; no new caller-side initialization protocol is introduced.
- Affected docs: workload-chain architecture, verification semantics, and any guidance that currently implies only the `default` chain has explicit baseline origin semantics.