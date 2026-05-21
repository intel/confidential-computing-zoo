## Why

Docktap explicit delegation currently works as a low-level authorization mechanism, but its main user path is still too close to the underlying implementation: callers encounter runtime authorization challenges, must understand OIDC login state, and often have to create delegation explicitly through the raw API. That shape is workable for operators and debugging, but it is too brittle as the default path for agent workflows and too low-level for fixed-script or wrapper-based workloads.

The project needs a higher-level authorization-readiness surface now so callers can prepare Docktap authorization before container work begins while keeping delegation policy under tc-api control. This allows non-invasive integration through skills or wrappers without turning OpenClaw or Hermes into special-case lifecycle dependencies.

## What Changes

- Introduce a high-level Docktap authorization-readiness capability that lets external callers ensure runtime authorization is ready before Docker-backed work starts.
- Move delegation defaults under service-side policy so TTL and scope are provided by tc-api/Docktap defaults rather than by agent-side task estimation.
- Add a skill/wrapper-friendly readiness flow that can report existing authorization, create delegation when needed, and return a stable readiness summary for callers.
- Keep the raw delegation API available as a lower-level operator/debug path instead of treating it as the primary product entry point.
- Preserve Docktap runtime challenge behavior as a fallback path when callers do not preflight authorization.
- Explicitly keep OpenClaw and Hermes integration non-invasive in this change: they may consume the new readiness capability through skills or wrappers, but this change does not modify their core lifecycle code.

## Capabilities

### New Capabilities
- `docktap-authorization-readiness`: High-level readiness semantics for ensuring Docktap runtime authorization is available to agent skills, wrappers, and fixed-code launch paths without exposing raw delegation mechanics as the primary interface.

### Modified Capabilities
- `session-delegation`: Delegation behavior changes so service-side policy supplies default TTL and scope, and delegation creation/readiness is positioned as part of a higher-level authorization flow instead of only a raw create-delegation step.

## Impact

- Affected code: Docktap delegation policy/config, delegation API support, Docktap authorization challenge shaping, and any new readiness-oriented API surface in tc-api.
- Affected APIs: the existing `POST /api/docktap/delegate` endpoint remains but is no longer the preferred top-level entry; a new readiness-oriented capability is expected for skill/wrapper consumption.
- Affected integrations: OpenClaw/Hermes-style agent integrations, fixed-script workloads, operator workflows, and any client that currently relies on raw delegation creation.
- Dependencies/systems: OIDC/Sigstore login flow, TruCon delegation storage and lookup, Docktap runtime authorization checks, and external skill or wrapper packaging.