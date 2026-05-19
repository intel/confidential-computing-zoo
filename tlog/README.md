# tlog

Standalone trusted-log core package.

`tlog` is the low-dependency foundation shared by the higher-level services in this repository. It provides the core domain types, abstract interfaces, error classes, and deterministic digest helpers used by TruCon and backend adapters.

## What It Contains

- Domain dataclasses such as `Entry`, `Record`, `EventLog`, `RecordContext`, and `CommitResult`
- Queue and verification result types such as `CommitQueueStatus`, `LatestState`, and `VerificationResult`
- Abstract interfaces such as `ImmutableLogAdapter` and `LocalMRAdapter`
- Stable digest helpers such as `canonical_json()`, `compute_entry_digest()`, and `compute_event_digest()`
- Shared trusted-log error types

## Scope

`tlog` is intentionally narrow:

- no FastAPI or service runtime code
- no Rekor-specific logic
- no container orchestration logic
- minimal third-party dependency surface

Use this package when you need the trusted-log data model or digest rules without pulling in the rest of the control plane.

## Install

```bash
cd tlog
python -m pip install -e .
```

## Package Layout

```text
tlog/
├── pyproject.toml

└── tlog/
    ├── __init__.py
    ├── digest.py
    ├── errors.py
    ├── immutable.py
    ├── local_mr.py
    └── types.py
```

## Main Exports

Common imports are re-exported from `tlog` directly:

```python
from tlog import (
    Entry,
    Record,
    EventLog,
    CommitResult,
    ImmutableLogAdapter,
    LocalMRAdapter,
    canonical_json,
    compute_entry_digest,
    compute_event_digest,
)
```

## Development Notes

- Source lives under `tlog/`
- The package targets Python 3.11+
- This package is intended to stay usable as an independent building block inside or outside this monorepo
