## 1. Adapter Interface Setup

- [x] 1.1 Create new `ImmutableLogAdapter` abstract base class with `submit()`, `get()`, and `traverse()` methods.
- [x] 1.2 Create `tlog_impl.py` (or similar) to house the implementation.

## 2. Sigstore Implementation

- [x] 2.1 Extract hardcoded Sigstore submit and get logic from `api.py` into a new `SigstoreLogAdapter` class.
- [x] 2.2 Implement `traverse()` logic within `SigstoreLogAdapter` conforming to the adapter interface.
- [x] 2.3 Add unit tests specifically testing `SigstoreLogAdapter` mapping, including `traverse` backward log traversal.

## 3. Refactoring api.py

- [x] 3.1 Refactor `api.py` to accept or instantiate an `ImmutableLogAdapter` (e.g. `SigstoreLogAdapter`).
- [x] 3.2 Replace all direct calls to transparency log processes inside `api.py` with calls to the adapter interface.
- [x] 3.3 Ensure existing integration tests for `api.py` pass with decoupled adapter.