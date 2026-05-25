# OpenViking Verifier/Policy Gateway Notes

This directory documents an optional verifier/policy gateway or sidecar for OpenViking integration. It does not contain gateway implementation code in this change.

## Suitable Use

A gateway is useful when OpenClaw talks to OpenViking over a stable HTTP boundary and trust establishment can be decided from metadata, evidence, route class, policy, and scope.

Recommended responsibilities:

- expose or proxy evidence and posture claims
- verify attestation before allowing sensitive routes
- classify routes as observe, recall, materialize, commit, privacy_restore, or egress
- inject scoped headers or capability leases when policy allows
- record metadata-only decision events
- fail closed when verification or policy is unavailable

## Metadata-Only Constraint

A gateway outside the confidential boundary must not inspect or persist session plaintext. It may use:

- route path and method
- subject and tenant identifiers or hashes
- payload class
- payload digest
- policy id and version
- evidence digest
- lease id hash

It must not store prompts, tool outputs, archive plaintext, privacy-restored values, or raw memory values.

## Route Policy Responsibilities

The gateway policy should distinguish:

- status and posture routes
- recall routes
- materialization routes
- observe/session-write routes
- commit routes
- egress routes
- privacy-restore paths

Materialization and privacy restore require stronger policy than summary recall.

## Anti-Patterns

Avoid these designs:

- plaintext-inspecting gateway outside the confidential boundary
- gateway-local replay store for raw sessions
- best-effort verification that allows context transfer after errors
- treating content read or archive expansion as ordinary recall
- logging request or response bodies into the trusted decision ledger

## Limits

Gateway mode reduces OpenViking interface-level intrusion, but it cannot fully replace OpenViking-side hooks for privacy restore, archive materialization, memory extraction, and external model or embedding egress.