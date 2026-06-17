## Context

The current trusted-log subsystem is split across three sibling Python projects at the repository root: `tlog/` for shared types and adapter contracts, `tlog-rekor/` for the production Rekor implementation, and `tlog-onchain/` for the placeholder on-chain implementation. That split keeps the `tlog` core free of heavy backend dependencies, but it also creates operational and structural overhead in a monorepo where Rekor is the only production backend and on-chain is still a scaffold.

This change adopts a consolidation model where `tlog` remains the standalone trusted-log distribution, but backend implementations move under an internal namespace such as `tlog.backends.rekor` and `tlog.backends.onchain`. The goal is to reduce project count without collapsing the architectural distinction between shared contracts and concrete backend integrations.

## Goals / Non-Goals

**Goals:**
- Reduce the number of top-level trusted-log Python projects from three to one.
- Preserve a clear separation between core trusted-log contracts and concrete backend implementations.
- Keep the base `tlog` install low-dependency while making backend dependencies opt-in through extras.
- Replace first-party imports of `tlog_rekor` and `tlog_onchain` with stable paths under `tlog.backends`.
- Simplify monorepo setup, Docker copy rules, and editable-install flows around one trusted-log distribution.

**Non-Goals:**
- Redesigning the `ImmutableLogAdapter` contract or backend behavior.
- Implementing real on-chain backend functionality.
- Preserving the old `tlog_rekor.*` and `tlog_onchain.*` import paths indefinitely.
- Moving backend orchestration back into `tc_api.trucon.adapters`.

## Decisions

### 1. Consolidate distributions, not architectural layers
Backend implementations move into the `tlog` project, but they remain under explicit backend namespaces such as `tlog.backends.rekor` and `tlog.backends.onchain` rather than mixing directly into the core `tlog` package root.

Why:
- Reduces monorepo package count without making backend code indistinguishable from core types and digest logic.
- Keeps future backend growth organized under one predictable subtree.
- Preserves the mental model that `tlog` core is the contract layer and `tlog.backends.*` are concrete implementations.

Alternative considered:
- Flattening backend modules directly into `tlog/` (for example `tlog.rekor_adapter`). Rejected because it blurs the core/backend boundary and scales poorly if more backends appear.

### 2. Keep base `tlog` install lean with optional extras
The `tlog` distribution will remain installable without backend-specific dependencies, while backend integrations will be exposed through optional dependency groups such as `tlog[rekor]` and future `tlog[onchain]`.

Why:
- Preserves the current advantage that shared types and digest logic do not force Sigstore dependencies onto all consumers.
- Lets `tc-api` depend on the specific backend features it actually uses.
- Avoids turning package consolidation into dependency bloat.

Alternative considered:
- Moving Rekor dependencies into base `tlog`. Rejected because it would punish lightweight consumers of core trusted-log types.

### 3. First-party code migrates atomically to `tlog.backends.*`
Repository-owned imports will move from `tlog_rekor.*` and `tlog_onchain.*` to `tlog.backends.rekor.*` and `tlog.backends.onchain.*` in one coordinated change. No long-lived sibling compatibility packages are planned inside the monorepo.

Why:
- The main purpose of the change is to remove sibling backend projects; preserving old packages indefinitely would undermine that goal.
- Atomic migration is feasible because all first-party import sites live in the same monorepo.
- It keeps the final package surface simpler and easier to document.

Alternative considered:
- Keeping tiny shim packages for `tlog-rekor` and `tlog-onchain`. Rejected for the mainline design because it preserves package-count overhead and complicates the end state.

### 4. `tc-api` setup and container flows pivot to one trusted-log project input
Editable installs, Docker COPY rules, and local setup documentation will reference the consolidated `tlog/` project only, with extras or internal modules handling backend availability.

Why:
- Package consolidation only pays off if the surrounding developer and deployment workflows simplify too.
- Current setup comments and image build steps still reflect a multi-project model.

Alternative considered:
- Only changing Python import paths while keeping multiple build/install inputs. Rejected because it captures the migration cost without the operational simplification.

## Risks / Trade-offs

- [Base package boundaries become muddier] → Keep backend code under `tlog.backends.*` and document that `tlog` root remains core-focused.
- [Optional extras may be underused, causing missing backend dependencies at runtime] → Make backend-dependent first-party install paths explicit in setup docs and package metadata.
- [Import-path migration touches many tests and scripts] → Update first-party imports atomically and validate with targeted trusted-log and TruCon test slices.
- [Existing specs currently encode sibling backend packages as architecture] → Update the affected layout and packaging specs in the same change so implementation and architecture stay aligned.
- [External users may rely on `tlog_rekor` paths] → Mark the change as breaking, document the new import paths, and avoid pretending compatibility exists when it does not.