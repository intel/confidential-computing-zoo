## Context

Docktap now has explicit read-only observation types for container listing and exec flows, but multi-resource name/probe traffic still leaks into broad fallback buckets. In normal Docker control-plane behavior, a user-facing name can be probed across several resource families before the client or daemon decides what object it refers to. Today that activity is hard to interpret because only `image_inspect` has a dedicated label, container detail remains a generic `inspect`, and network/volume/plugin lookups are not represented as first-class observations.

This change is intentionally narrower than a full taxonomy redesign. It focuses on making probe traffic readable while preserving existing compatibility for image and container inspect labels.

## Goals / Non-Goals

**Goals:**
- Add explicit read-only classifications for high-frequency probe paths in the network, volume, and plugin families.
- Keep existing `image_inspect` behavior backward compatible.
- Keep container detail inspection backward compatible as `inspect`.
- Reduce accidental `unknown` usage for these probe families without making “unknown elimination” the primary goal.
- Document that `404` normal-miss outcome semantics are deferred to `GAP-21.4`.

**Non-Goals:**
- Rename existing container detail `inspect` to `container_inspect`.
- Introduce a generic `resource_probe` abstraction or a new `resource.kind` metadata contract.
- Reclassify write paths such as create/delete/connect/enable operations for these resources.
- Define `ok` / `miss` / `error` outcome semantics for resource probe responses.

## Decisions

### Decision: Use distinct resource-specific observation labels

This change will add explicit labels such as `network_inspect`, `volume_inspect`, and `plugin_inspect` rather than creating a shared abstract `resource_probe` type.

- Alternative considered: one generic probe label plus `resource.kind` metadata.
- Why not: it introduces a broader metadata contract and a more opinionated taxonomy redesign than the current gap requires.

### Decision: Preserve existing `inspect` and `image_inspect` compatibility

Container detail inspection remains `inspect`, and image lookup remains `image_inspect`.

- Alternative considered: normalize all inspect-style paths into resource-specific names.
- Why not: that turns a targeted gap closure into a backward-compatibility break for existing log consumers.

### Decision: Scope the first wave to read-only GET probe paths

This proposal covers read-only probe/inspect endpoints only, not state-changing operations in the same resource families.

- Alternative considered: include write paths such as network connect/disconnect or plugin enable/disable.
- Why not: those are not read-only probe traffic and would blur the distinction between observation and lifecycle/control semantics.

### Decision: Treat `404` meaning as deferred

This change answers “what resource family was probed,” not “was the probe a normal miss.” Outcome semantics remain the responsibility of `GAP-21.4`.

- Alternative considered: introduce miss/error classification in the same change.
- Why not: it couples two adjacent but distinct concerns and makes the proposal less focused.

## Risks / Trade-offs

- [New labels increase taxonomy surface area] → Keep the first wave intentionally small and tied to clear high-frequency probe families.
- [Container detail inspect remains a generic legacy label] → Document that compatibility is intentional and may be revisited only in a broader taxonomy change.
- [Logs may still show ambiguous failures until `GAP-21.4`] → Make the defer boundary explicit in specs and docs so partial readability is intentional.
- [Unknown bucket will still exist after this change] → Define success as resource-family clarity, not total unknown elimination.

## Migration Plan

1. Add explicit classifier mappings and focused tests for the selected read-only resource probe paths.
2. Update docs to separate probe-family observation labels from lifecycle commit types and from deferred outcome semantics.
3. Leave trusted-event submission, lifecycle parent-linking, and response outcome meaning unchanged.
4. Roll back by removing the new resource-specific labels if downstream tooling cannot absorb them, without affecting request forwarding behavior.

## Open Questions

- Should plugin probe classification stay specific to `/plugins/{name}/json`, or should future work fold in other read-only plugin metadata endpoints?
- If a later change introduces `resource.kind`, should these distinct labels stay as canonical types or become compatibility aliases?