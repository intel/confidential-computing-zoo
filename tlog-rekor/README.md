# tlog-rekor

Sigstore / Rekor backend adapter package for `tlog`.

`tlog-rekor` contains the Rekor-facing implementation of the `tlog.ImmutableLogAdapter` contract, plus OCI mirror helpers used to persist and resolve bundle material outside Rekor.

## What It Contains

- `SigstoreLogAdapter` for Rekor submission, lookup, traversal, and payload-hash-based search
- `OciBundleMirror` for local OCI-layout storage or registry-backed OCI repositories
- `build_mirror_annotations()` helpers for bundle mirror metadata

## Scope

`tlog-rekor` sits above `tlog` and below service code:

- depends on `tlog`
- contains Rekor- and Sigstore-specific integration logic
- does not contain FastAPI service orchestration
- does not contain TruCon queue management

## Install

```bash
cd tlog-rekor
python -m pip install -e .
```

## Package Layout

```text
tlog-rekor/
├── pyproject.toml
└── tlog_rekor/
    ├── __init__.py
    ├── adapter.py
    └── oci_mirror.py
```

## Main Exports

```python
from tlog_rekor import SigstoreLogAdapter, OciBundleMirror, build_mirror_annotations
```

## Notes

- `SigstoreLogAdapter` supports Rekor bundle submission and replay-oriented reads.
- `OciBundleMirror` supports both local filesystem-backed OCI layout storage and registry-backed repositories.
- This package is intended to remain usable independently of the `tc-api` service layer.
