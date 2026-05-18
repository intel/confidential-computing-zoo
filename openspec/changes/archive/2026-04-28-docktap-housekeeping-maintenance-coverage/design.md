## Context

Docktap now documents four layers for mixed Docker trace reading: API-path observation, daemon/internal phase taxonomy, normalized task-transition vocabulary, and secondary runtime interpretation for healthcheck-like exec flows and attach activity. What remains missing is a narrow interpretation layer for housekeeping activity that appears after primary and secondary runtime sequences have already completed.

`GAP-22.5` sits after taxonomy, correlation, and secondary-runtime interpretation. The source evidence in `openclaw-docker-analysis.md` is currently strongest for post-exec cleanup, especially `clean 2 unused exec commands`, and much weaker for a broader maintenance taxonomy. The design therefore needs to define a first-wave housekeeping contract that is evidence-led and operator-facing without turning this change into parser design, Docktap-local retention guidance, or a universal maintenance framework.

## Goals / Non-Goals

**Goals:**
- Define a documentation-first interpretation contract for daemon/internal housekeeping and post-runtime maintenance activity in mixed Docker traces.
- Treat first-wave housekeeping primarily as post-exec cleanup and similar maintenance residue rather than as a broad maintenance taxonomy.
- Define how housekeeping should be read relative to primary lifecycle and secondary runtime activity.
- Define a minimal expected-noise versus investigation-worthy boundary for housekeeping patterns.
- Preserve room for later maintenance families such as image GC, background scanning, and retry or reconcile loops without treating them as fully specified now.

**Non-Goals:**
- Define a parser, ingestion surface, or machine confidence model for housekeeping detection.
- Reinterpret healthcheck-like exec flows or attach semantics already covered by `daemon-secondary-runtime-interpretation`.
- Define Docktap-local retention, retry cleanup, or sidecar GC semantics.
- Define alert thresholds, anomaly scoring, or operational automation rules.
- Claim a complete taxonomy for all future maintenance behavior.

## Decisions

### Decision: Treat `GAP-22.5` as an interpretation layer, not a new event model
The change will explain how to read housekeeping activity in mixed traces rather than introducing a parser-facing maintenance event schema.

- Alternative considered: define a normalized housekeeping event model immediately.
- Why not: the current evidence is documentation-led and too narrow to justify a stable machine contract.

### Decision: Scope the first wave around post-exec cleanup
The first-wave contract will center on post-runtime cleanup evidence such as `clean 2 unused exec commands` and similar maintenance residue that follows exec activity.

- Alternative considered: define a broad housekeeping catalog covering scanning, image GC, and reconcile loops now.
- Why not: those broader families are not yet supported by equally strong mixed-trace evidence in this repo.

### Decision: Model housekeeping as post-runtime maintenance context
Housekeeping will be documented as a layer that follows primary lifecycle and secondary runtime activity rather than as part of either workload path.

- Alternative considered: fold housekeeping into secondary runtime because both often appear after create/start.
- Why not: secondary runtime still describes daemon-managed exec activity, while housekeeping describes later maintenance work after those runtime flows complete.

### Decision: Allow contextual-first correlation for housekeeping
The first-wave contract will allow housekeeping to correlate to nearby runtime activity mostly through sequence position, local timing, and surrounding context rather than requiring stable object-level joins.

- Alternative considered: require stable container or exec identifiers for housekeeping interpretation.
- Why not: the strongest current housekeeping evidence does not consistently expose object identities, and a stricter rule would overfit beyond the trace evidence.

### Decision: Keep the first-wave signal boundary minimal
The change will define expected maintenance noise and only a small set of investigation-worthy shapes such as repeated housekeeping churn, unusual delay, or cleanup patterns that start to obscure interpretation of the primary runtime story.

- Alternative considered: define thresholds, scoring, or alert semantics now.
- Why not: that would turn an interpretation contract into a monitoring design before the evidence model is mature.

### Decision: Explicitly separate daemon housekeeping from Docktap-local cleanup
The design will call out that daemon/internal housekeeping is distinct from Docktap-local retention helpers, retry cleanup, or sidecar GC behavior.

- Alternative considered: group all cleanup-like work under one maintenance heading.
- Why not: that would blur daemon trace interpretation with implementation-specific sidecar operational behavior already covered elsewhere.

## Risks / Trade-offs

- [First-wave housekeeping may overfit a single cleanup example] -> Keep the contract narrow, evidence-led, and explicit about extension room for later maintenance families.
- [Readers may confuse housekeeping with secondary runtime activity] -> Describe housekeeping as post-runtime maintenance context and contrast it directly with the existing secondary-runtime interpretation layer.
- [Weak object correlation may feel underspecified] -> State clearly that contextual-first correlation is intentional for the first wave because the current trace evidence is not object-rich.
- [Docktap-local cleanup could leak into scope] -> Make the daemon-versus-sidecar boundary explicit in proposal, design, and specs.

## Migration Plan

1. Add a new capability spec for daemon/internal housekeeping interpretation.
2. Update Docktap architecture and API documentation to define first-wave housekeeping scope, contextual correlation, and expected-noise versus investigation-worthy reading guidance.
3. Add representative mixed-trace examples from `openclaw-docker-analysis.md` showing housekeeping relative to preceding runtime activity.
4. Update `docs/overview_tasks.md` so `GAP-22.5` reflects the narrow interpretation-contract scope.
5. Keep runtime code, request classification, and prior GAP-22 contracts unchanged.

## Open Questions

- What additional trace evidence would be sufficient to promote broader maintenance families such as scanning or image GC from extension room into a first-class documented contract?
- Should future parser-facing work keep contextual-first housekeeping correlation as an explicit outcome class, or eventually compress it into a machine-oriented confidence model?
- When maintenance activity repeats across long traces, should future work describe aggregate churn patterns separately from local housekeeping interpretation?## Context

Docktap now documents four layers for reading mixed Docker traces: daemon/internal taxonomy, normalized task transitions, API/internal correlation, and secondary runtime interpretation. What remains missing is a stable interpretation layer for daemon housekeeping and internal maintenance activity that appears after primary lifecycle and secondary runtime work have already completed.

`GAP-22.5` sits after the earlier runtime-interpretation tasks and should stay documentation-first. The current first-source evidence is strongest for post-exec cleanup activity such as `clean 2 unused exec commands`, while evidence for broader maintenance families like image GC, background scanning, or retry/reconcile loops is still too thin for a strong first-wave contract. The design therefore needs to define a narrow housekeeping interpretation contract without turning this change into parser design, Docktap-local GC semantics, or a broad anomaly framework.

## Goals / Non-Goals

**Goals:**
- Define a documentation-first interpretation contract for daemon/internal housekeeping and post-runtime maintenance activity in mixed Docker traces.
- Keep the first-wave scope conservative around exec-cleanup-style maintenance evidence.
- Define how housekeeping should be read relative to primary lifecycle activity and secondary runtime activity.
- Define a small first-wave boundary between expected maintenance noise and investigation-worthy housekeeping patterns.
- Preserve room for later maintenance families without requiring the taxonomy to be redesigned.

**Non-Goals:**
- Define a parser, ingestion surface, or machine confidence model for housekeeping detection.
- Redefine the primary lifecycle, API/internal correlation, or secondary runtime interpretation contracts.
- Recast Docktap-local retention, retry cleanup, or sidecar sweeper behavior as daemon housekeeping.
- Define a full anomaly engine, threshold model, or alerting contract for maintenance behavior.
- Fully specify broader maintenance families such as image GC, background scanning, or retry/reconcile loops from limited current evidence.

## Decisions

### Decision: Treat housekeeping as a post-runtime interpretation layer, not a runtime path
`GAP-22.5` will describe housekeeping as maintenance context that follows or surrounds already-interpreted runtime activity rather than as part of the primary or secondary runtime path itself.

- Alternative considered: model housekeeping as an extension of secondary runtime activity.
- Why not: cleanup and maintenance residue are better read as after-effects around runtime execution, not as workload or healthcheck execution themselves.

### Decision: Scope the first wave to exec-cleanup-centered evidence
The first implementation surface will anchor on maintenance lines such as `clean 2 unused exec commands` and similarly narrow post-exec cleanup context.

- Alternative considered: define a broader daemon maintenance framework up front.
- Why not: the current evidence base strongly supports exec cleanup but does not yet support a stable first-wave contract for broader maintenance families.

### Decision: Allow contextual rather than object-precise correlation
Housekeeping interpretation will allow contextual correlation to nearby runtime activity based on local sequence position, timing, and surrounding trace structure rather than requiring a strong container ID or exec ID join in every case.

- Alternative considered: require stable object-level joins similar to create/start/exec correlation.
- Why not: current housekeeping evidence may not expose strong identifiers, and requiring them would make the first-wave contract too brittle.

### Decision: Separate expected maintenance noise from investigation-worthy signals conservatively
The first-wave contract will distinguish normal delayed cleanup after runtime activity from a small set of patterns that deserve later investigation, such as repeated or unusually persistent maintenance churn.

- Alternative considered: define alert thresholds, anomaly scores, or automated severity levels now.
- Why not: those choices depend on parser and operational evidence that are explicitly out of scope for this documentation-first phase.

### Decision: Keep broader maintenance families as explicit extension room
The design will reserve room for image GC, background scanning, and retry/reconcile loops as future housekeeping subfamilies without claiming they are already fully specified.

- Alternative considered: omit future families entirely until more traces are collected.
- Why not: the docs should show how the model can grow later, as long as that extension room is clearly marked as future work rather than current contract.

### Decision: Keep Docktap-local cleanup semantics out of scope
Docktap's local retention and retry cleanup mechanisms remain a separate operational concern and will not be folded into daemon/internal housekeeping interpretation.

- Alternative considered: unify all cleanup-like behavior under one maintenance umbrella.
- Why not: that would conflate daemon-internal trace interpretation with sidecar-local operational state management and blur a useful system boundary.

## Risks / Trade-offs

- [The first-wave contract may overfit one cleanup example] → Keep the scope narrow, explicitly centered on exec-cleanup-style evidence, and describe broader maintenance families only as extension room.
- [Contextual correlation may feel weaker than earlier GAP-22 joins] → State explicitly that housekeeping often lacks strong object identifiers and therefore relies more on local sequence context.
- [Readers may confuse housekeeping with Docktap-local GC or retry cleanup] → Reassert the daemon/internal versus sidecar-local boundary in proposal, design, and specs.
- [Signal guidance may drift into alerting design] → Keep the first-wave distinction limited to expected noise versus worth-investigating patterns without thresholds or scoring.

## Migration Plan

1. Add a new capability spec for housekeeping and internal-maintenance interpretation.
2. Update Docktap architecture and API documentation to position housekeeping relative to primary lifecycle and secondary runtime flows.
3. Add representative mixed-trace examples showing post-exec cleanup as expected maintenance context and document the minimal signal boundary.
4. Update `docs/overview_tasks.md` so `GAP-22.5` reflects the narrower first-wave housekeeping scope and remains distinct from Docktap-local cleanup and earlier GAP-22 runtime tasks.
5. Keep runtime code, request classification, and existing GAP-22 interpretation behavior unchanged.

## Open Questions

- What additional mixed-trace evidence would be sufficient to promote image GC, background scanning, or retry/reconcile loops from extension room into first-class housekeeping coverage?
- Should later parser-facing work preserve the distinction between contextual housekeeping correlation and strong object-level joins, or collapse them into one confidence model?
- When future maintenance families are added, should the docs define explicit housekeeping subcategories or continue using one interpretation layer with representative examples?