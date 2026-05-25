# Threat Model

This document captures assumptions and safety rules for the Confidential Memory Control Plane documentation. It is not a formal verification claim.

## Assets

Sensitive assets include:

- user prompts and assistant responses
- tool inputs and outputs
- session archives and replay material
- raw memory values and extracted facts
- privacy-restored values
- tenant keys and key handles
- policy trust roots
- evidence and ledger heads used for verification

## Control-Plane Assets

Control-plane metadata is less sensitive than plaintext but still security-relevant:

- operation names
- subject and workspace hashes
- resource scope hashes
- policy ids and versions
- evidence digests
- payload digests
- decision results
- denial reasons
- ledger chain identifiers and head references

This metadata can reveal usage patterns and must be scoped and retained deliberately.

## Assumptions

- Memory frameworks keep their own memory data-plane implementations.
- `core/tlog` can provide reusable digest and trusted-log concepts for future implementations.
- `core/tc-api`, TruCon, and `tc-verify` may provide optional attested-ledger and verification integrations.
- Non-confidential hosts and gateways are not trusted with memory plaintext.
- External LLMs, embedding providers, analytics, and telemetry sinks are outside the confidential boundary unless separately attested and authorized.

## Plaintext Handling Rules

The trusted decision ledger must not record:

- prompt plaintext
- tool-result plaintext
- raw session archives
- raw memory content
- privacy-restored secret values
- credentials or tokens

The ledger may record:

- canonical metadata
- hashes and digests
- scope identifiers
- policy identifiers
- evidence references
- lease references
- decision outcomes

## Fail-Closed Rules

Sensitive operations should fail closed when:

- evidence cannot be fetched or verified
- evidence is expired
- policy evaluation is unavailable
- a required lease is missing or invalid
- required ledger recording fails
- egress destination cannot be classified
- key-release evidence does not match policy

For OpenClaw/OpenViking, failure to verify the target OpenViking or gateway evidence should deny context transfer.

## Gateway Anti-Patterns

Avoid these designs:

- a plaintext-inspecting gateway outside the confidential boundary
- a gateway that stores raw sessions, tool outputs, or privacy-restored values
- a route policy that treats raw materialization the same as summary recall
- a best-effort policy check that allows context transfer when verification is unavailable
- a logging layer that copies request or response bodies into the trusted decision ledger

## Trusted Decision Ledger Sensitivity

The ledger is evidence, not a memory store. It should prove that decisions occurred under specific policy and evidence. It should not become an alternate repository of private memory content.

## Residual Risks

- Hashes of sensitive payloads can still be correlation handles.
- Metadata can leak high-level activity patterns.
- A compromised adapter can misclassify payload class or operation type.
- A gateway can only enforce what it can observe.
- Runtime-internal state mutations require runtime hooks or confidential runtime boundaries.

These risks should guide future implementation proposals and tests.