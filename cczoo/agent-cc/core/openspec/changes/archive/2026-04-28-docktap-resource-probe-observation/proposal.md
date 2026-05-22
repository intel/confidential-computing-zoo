## Why

Docktap still collapses multi-resource name/probe traffic into generic `inspect` or `unknown` buckets, which makes Docker control-plane traces hard to read when the client resolves a name across container, network, volume, and plugin resources. After `container_list` and exec-path coverage, the next high-value gap is to make these read-only resource probes visible without redesigning lifecycle semantics.

## What Changes

- Add explicit read-only observation classifications for high-frequency Docker resource probe paths in the network, volume, and plugin families.
- Preserve backward compatibility for existing `image_inspect` and container detail `inspect` behavior rather than renaming current buckets.
- Document the boundary that benign `404` miss semantics are deferred to a later change, so this change focuses on resource-family classification only.
- Keep trusted-event submission and lifecycle parent-linking behavior unchanged.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `sock-bridge-lifecycle-classification`: Extend Docktap's canonical request classification contract so multi-resource probe traffic no longer falls through generic fallback buckets and remains clearly separated from lifecycle commit types.

## Impact

- Affected code: `docktap/proxy/operation_log.py`, focused classifier/proxy tests, and Docktap architecture/API docs.
- Affected APIs: Docker Engine API observation for read-only network, volume, and plugin probe paths.
- Affected systems: Docktap runtime observability, Docker name-resolution trace readability, and downstream consumers that group read-only observation traffic by resource family.