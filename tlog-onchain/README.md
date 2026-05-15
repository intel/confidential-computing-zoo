# tlog-onchain

On-chain backend adapter package for `tlog`.

`tlog-onchain` is the on-chain counterpart to `tlog-rekor`. At the moment it is a scaffold package that defines the adapter boundary and package shape for future on-chain immutable-log support.

## Current State

The package currently exports `OnChainLogAdapter`, a placeholder implementation of the `tlog.ImmutableLogAdapter` interface. Its methods intentionally raise `NotImplementedError` until a concrete on-chain backend is added.

## Install

```bash
cd tlog-onchain
python -m pip install -e .
```

## Package Layout

```text
tlog-onchain/
├── pyproject.toml
└── src/tlog_onchain/
    ├── __init__.py
    └── adapter.py
```

## Main Export

```python
from tlog_onchain import OnChainLogAdapter
```

## Intended Role

When implemented, this package is expected to:

- satisfy the `tlog.ImmutableLogAdapter` contract
- provide submit / fetch / traverse behavior for an on-chain log backend
- remain separate from `tc-api` runtime orchestration and HTTP service code

Until then, treat it as a reserved extension point rather than a production-ready backend.
