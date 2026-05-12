## Context

The current `api.py` module in the `trusted_container_log` package contains hardcoded implementations of Sigstore transparency log interactions. This prevents the system from easily switching to other transparency log implementations or providing a unified `TransparentLogImpl` interface according to the architecture. Furthermore, the ability to traverse multiple log links (the `traverse()` method) hasn't been implemented yet. Extracting an `ImmutableLogAdapter` is essential to correct the architecture.

## Goals / Non-Goals

**Goals:**
- Extract Sigstore-specific code out of `api.py` and into `tlog_impl.py` or a similarly named module.
- Create an abstract or clearly defined `ImmutableLogAdapter` interface with at least `submit()`, `get()`, and `traverse()` methods.
- Implement the `traverse()` method in the new adapter based on the Sigstore response structure.
- Refactor `api.py` to instantiate and use this adapter instead of direct hardcoded implementation.

**Non-Goals:**
- Do not implement any non-Sigstore log adapter in this change (only create the interface and the initial Sigstore implementation).
- Do not change the outward-facing API routes/semantics of `trusted_container_log`, except as needed to support `traverse`.

## Decisions

- **Adapter Interface**: Create a `class ImmutableLogAdapter(ABC)` containing the desired methods (`submit`, `get`, `traverse`) to enforce the contract.
- **Sigstore Implementation**: Create `class SigstoreLogAdapter(ImmutableLogAdapter)` which wraps the current `subprocess` logic or Rekor HTTP API calls being used in `api.py`.
- **Traverse Implementation**: `traverse()` will recursively or iteratively follow previous entry links/hashes until it hits the genesis entry or a specified depth. 

## Risks / Trade-offs

- **Risk**: Refactoring might break existing logic in `api.py` that relies heavily on Sigstore-specific output.
  - *Mitigation*: Ensure robust unit tests for the transition, or run integration tests against a local Rekor instance.
- **Risk**: Developing `traverse()` for Sigstore requires understanding of the exact return format (HashedRekord/LogEntry) to extract the parent links.
  - *Mitigation*: Use reference outputs from existing test data (e.g., `entry1.json`, `entry2.json` in the `tlog` folder) to mock and verify traverse behavior.