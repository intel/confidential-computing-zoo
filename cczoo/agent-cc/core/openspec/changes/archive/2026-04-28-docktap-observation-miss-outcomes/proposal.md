## Why

Docktap can now tell which resource family a read-only probe targeted, but it still logs probe misses as plain HTTP failures. That leaves normal Docker control-plane checks, especially expected `404` responses during image and multi-resource name probing, looking indistinguishable from real proxy or daemon errors.

## What Changes

- Add explicit observation outcome semantics for read-only probe traffic so Docktap can distinguish `ok`, benign `miss`, and `error` results.
- Treat `404` responses for selected probe-style observation types as normal misses rather than generic failures.
- Keep proxy/local transport failures distinguishable from daemon-level `404` responses.
- Keep lifecycle trusted-event submission and TruCon `operation_result` semantics unchanged.
- Defer container detail inspect `404` handling and broader read-only endpoint outcome modeling to later changes.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `sock-bridge-lifecycle-classification`: Extend Docktap's observation contract so selected read-only probe operations record stable `ok` / `miss` / `error` outcome semantics without changing lifecycle submission boundaries.

## Impact

- Affected code: `docktap/proxy/operation_log.py`, response enrichment helpers, focused observation tests, and Docktap architecture/API docs.
- Affected APIs: Docker Engine API observation for `image_inspect`, `network_inspect`, `volume_inspect`, and `plugin_inspect` responses.
- Affected systems: Docktap local observability, mixed Docker trace interpretation, and downstream tooling that needs to separate expected probe misses from genuine runtime/proxy failures.