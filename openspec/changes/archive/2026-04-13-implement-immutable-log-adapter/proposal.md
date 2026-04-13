## Why

The current implementation of the ImmutableLogAdapter lacks proper decoupling. The architectural design requires a unified interface with `submit()`, `get()`, and `traverse()` methods. However, in the current codebase, some Sigstore-specific logic is hardcoded directly into `api.py`. It has not been properly extracted into an independent `TransparentLogImpl` component. Furthermore, the method to traverse the transparent log chain by links (`traverse()`) is completely missing.

## What Changes

- Extract the Sigstore-specific logic currently hardcoded in `api.py` into a new, independent `TransparentLogImpl` (or generic ImmutableLogAdapter) component.
- Provide a unified interface for the ImmutableLog implementation, which must at minimum include `submit()`, `get()`, and `traverse()`.
- Implement the missing `traverse()` method to allow traversing the transparent log by links.
- Modify `api.py` to use the decoupled `TransparentLogImpl` instead of hardcoded Sigstore logic.

## Capabilities

### New Capabilities
- `immutable-log-traverse`: Traversing the transparent log chain by links.
- `immutable-log-adapter`: A unified and decoupled interface for transparent log actions (`submit`, `get`, `traverse`).

### Modified Capabilities


## Impact

- `trusted_container_log/api.py`: Will be refactored to remove hardcoded Sigstore logic and use the new adapter interface.
- New adapter module(s) will be created (e.g., `trusted_container_log/tlog_impl.py`).
- Potential impact on tests that assume the current `api.py` structure or test the log interactions.