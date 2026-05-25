# Trusted Decision Event Vocabulary

This vocabulary defines control-plane events for confidential agent memory. Events are metadata-only. They prove what security decision was made, under which policy and evidence, without storing memory plaintext.

## Generic Memory Operations

| Operation | Meaning | Sensitivity note |
|---|---|---|
| `observe` | Capture a prompt, tool event, message batch, or session event into a memory framework | Record only payload digests and classes |
| `recall` | Retrieve summaries, facts, memory snippets, persona blocks, or context candidates | Lower sensitivity than raw expansion, but still policy-controlled |
| `materialize` | Expand raw archives, raw tool results, refs, evidence chains, or privacy-restored content | High sensitivity; always first-class policy and ledger event |
| `commit` | Consolidate, compact, archive, summarize, or publish memory state | Should record output digests and policy version |
| `delete` | Governance delete, user delete, TTL expiry, or right-to-forget operation | Should record scope and deletion mode |
| `egress` | Send memory-derived data to external LLMs, embedding providers, analytics, exports, or telemetry | Requires destination and payload class |
| `privacy_restore` | Replace placeholders or protected references with sensitive plaintext inside a confidential boundary | Treat as materialization-sensitive |
| `key_release` | Release a key, key handle, or unseal permission | Requires verified evidence and policy |
| `lease` | Issue, validate, or revoke a scoped capability | Should be short-lived and purpose-bound |

## Event Names

Recommended event names are dot-separated and action-oriented:

```text
policy.decision.allow
policy.decision.deny
policy.decision.fail_closed
lease.issued
lease.revoked
key_release.allow
key_release.deny
egress.allow
egress.deny
materialize.allow
materialize.deny
observe.accepted
observe.rejected
recall.allow
recall.deny
commit.started
commit.completed
delete.completed
admin.policy.update
admin.trust_root.update
```

## Canonical Decision Predicate

A decision event should be canonicalizable for stable hashing. Example shape:

```json
{
  "event_type": "policy.decision.allow",
  "operation": "recall",
  "framework": "openviking",
  "deployment_id": "ov-prod-1",
  "subject_agent": "openclaw",
  "subject_user_hash": "sha256:...",
  "workspace_hash": "sha256:...",
  "resource_scope_hash": "sha256:...",
  "policy_id": "openviking-context-send",
  "policy_version": "2026-05-25",
  "evidence_digest": "sha384:...",
  "payload_class": "memory-summary",
  "payload_digest": "sha384:...",
  "result": "allow",
  "plaintext_logged": false
}
```

## Required Metadata Classes

Events should prefer these metadata classes:

- stable opaque identifiers
- subject and workspace hashes
- resource scope hashes
- policy id and policy version
- evidence digest or evidence head reference
- payload class and payload digest
- destination class for egress
- lease id hash for lease-backed decisions
- denial reason code for deny and fail-closed outcomes

## Prohibited Event Content

Trusted decision events must not contain:

- user prompt plaintext
- assistant response plaintext
- tool input or output plaintext
- session archive plaintext
- raw memory values
- privacy-restored secret values
- API keys, tokens, credentials, or private keys
- full local workspace paths when a stable opaque or hashed identifier is enough

## Materialization Events

`materialize.allow` and `materialize.deny` are first-class events because raw expansion is higher risk than ordinary recall.

Examples that should be treated as materialization:

- reading raw session archives
- expanding `result_ref` or `node_id` references
- reading `refs/*.md` raw tool logs
- restoring privacy placeholders to plaintext
- exporting replayable session history
- returning raw evidence attachments instead of summaries

## Relationship to `tlog`

Future implementations may represent these events with `tlog` concepts such as `Entry`, `Record`, `EventLog`, deterministic canonical JSON, and digest helpers. This document defines memory-specific event semantics; it does not add a runtime dependency or implementation.