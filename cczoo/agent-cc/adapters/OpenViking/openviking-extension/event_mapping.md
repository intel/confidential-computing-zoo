# OpenViking Route and Behavior Mapping

This document maps OpenViking/OpenClaw context-engine behavior to generic Confidential Memory Control Plane operations. It is documentation only.

## Context-Engine Chains

The existing OpenClaw plugin design describes three main paths:

- `afterTurn`: writes newly produced messages into OpenViking sessions
- `assemble`: recalls session and memory context before model calls
- `compact`: commits archives and memory extraction results

These map naturally to `observe`, `recall`, and `commit` operations.

## Route and Behavior Mapping

| OpenViking route or behavior | Control-plane operation | Notes |
|---|---|---|
| `/api/v1/system/status` | posture | May be allowed without memory scope, but should not substitute for evidence |
| readiness or health checks | posture | Operational only unless bound to evidence |
| `/api/v1/search/find` | recall | Summary or candidate retrieval |
| `/api/v1/sessions/{id}/context` | recall | Context assembly path |
| `/api/v1/sessions/{id}/messages` | observe | Session message capture |
| `/api/v1/sessions/{id}/commit` | commit | Archive and extraction boundary |
| `/api/v1/content/read` | materialize | May expose raw or restored content; high sensitivity |
| `/api/v1/sessions/{id}/archives/{archive_id}` | materialize | Archive expansion; high sensitivity |
| privacy placeholder restore | privacy_restore, materialize | Requires verified confidential boundary |
| memory extraction using external LLM | egress, commit | Egress before provider call; commit for result |
| external embedding provider | egress | Destination and payload class required |

## Policy Implications

Recall and materialization are separate operations. A policy that permits summary recall should not automatically permit raw content read, archive expansion, session replay, or privacy-restored content.

## Decision Event Examples

Recommended event names for OpenViking include:

- `openviking.context_send.allow`
- `openviking.context_send.deny`
- `openviking.recall.allow`
- `openviking.materialize.allow`
- `openviking.materialize.deny`
- `openviking.privacy_restore.allow`
- `openviking.egress.allow`
- `openviking.egress.deny`
- `openviking.commit.completed`

These events should be represented as metadata-only trusted decision events when integrated with the control plane.

## Gateway Boundary

A gateway can classify routes and perform prechecks, but OpenViking-side hooks are still needed for complete protection of internal privacy restore, archive materialization, memory extraction, and egress decisions.