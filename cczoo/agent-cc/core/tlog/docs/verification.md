# tlog Verification Primitives

This document describes the verification-relevant primitives that belong to the `tlog` package boundary.

It does not define one operator CLI, one evidence-export contract, or one application's verification policy.

## What `tlog` Contributes to Verification

At the package level, `tlog` contributes three things:

- deterministic digest rules
- shared result and error types
- adapter contracts that higher-level verifiers can build on

Everything else, such as replay policy, signer-identity policy, attestation binding, profile-specific checks, or troubleshooting modes, belongs to an integrating verifier rather than to `tlog` itself.

## Digest-Based Verification Building Blocks

### Entry Integrity

Each entry can be normalized and hashed independently with `compute_entry_digest()`.

That gives higher-level verifiers a stable unit for checking that:

- a field was serialized deterministically
- entry ordering was preserved
- event digests can be recomputed from persisted data

### Event Integrity

`compute_event_digest()` defines the package-level event digest contract:

- `created`
- `entry_digests`
- `event_id`
- `event_type`

A verifier that can reconstruct those fields can recompute the expected digest without knowing anything about the surrounding service topology.

## Result Vocabulary

The package provides `VerificationResult` as a minimal shared container:

```python
VerificationResult(
    success: bool,
    errors: list[str],
    details: dict[str, Any],
)
```

This is intentionally small. Integrations may extend their own result schemas, but they can still translate outcomes into this shared shape when a package-level return type is sufficient.

## Error Vocabulary

Verification-related failures can be surfaced through `VerificationError`, which preserves:

- `code`
- `message`
- `stage`
- `retryable`
- `details`

This keeps verification tooling from needing to invent ad hoc exception shapes for every backend or replay step.

## Adapter Roles in Verification

### `ImmutableLogAdapter`

Verification-oriented callers typically rely on these methods:

- `get_entry()` to retrieve one immutable-log record
- `traverse()` to walk history from a known tail
- `find_entries_by_payload_hash()` to discover candidate entries for a payload hash when a backend supports such lookup

The package contract intentionally stops there. It does not define:

- how many predecessors to fetch
- which candidate wins when multiple entries match
- how signatures are validated
- whether local caches are authoritative

Those are verifier-policy decisions.

### `LocalMRAdapter`

`LocalMRAdapter` can support verification workflows that correlate an event digest with a local measurement register surface.

The package does not define:

- which register index is authoritative
- which platform is targeted
- what external evidence format binds a measurement to an event history

Those are integration-specific concerns.

## Recommended Boundary

Package-level verification docs should stay limited to:

- canonical serialization rules
- hash contracts
- shared result containers
- adapter semantics

The following should be documented outside `tlog`:

- service-specific chain semantics
- runtime-specific measurement policies
- workload or launch verification profiles
- external operator evidence packages
- CLI modes and UX

## Example: Recompute an Event Digest

```python
from tlog import compute_entry_digest, compute_event_digest

entry_digests = [
    compute_entry_digest("artifact", "example.tar"),
    compute_entry_digest("size", 1234),
]

event_digest = compute_event_digest(
    event_id="evt-1",
    event_type="example.created",
    created_iso="2026-06-01T00:00:00+00:00",
    entry_digests=entry_digests,
)
```

That operation is pure package-level verification logic. It does not depend on any one backend or service.