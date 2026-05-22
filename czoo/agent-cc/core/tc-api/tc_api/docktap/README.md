# Docktap

Docktap is a Docker Unix socket proxy sidecar with operation tracking and JSON audit logging.

## Design Document

Detailed design and architecture are maintained in `../docs/docktap/architecture.md` for proxy specifics and `../docs/architecture.md` for system-level behavior, including
Docker request lifecycle details and endpoint-to-operation mapping used by the proxy.

Python-side API contracts and runtime-surface definitions are documented in `../docs/docktap/api.md`.

## Quick Start

```bash
cd docktap

# Start proxy runtime
python stream_test.py
```

In another terminal:

```bash
export DOCKER_HOST=unix:///tmp/test-stream.sock
docker pull nginx:alpine
```

## Testing

Pytest unit and integration tests live under `tests/docktap/` so they are collected with the rest of the project tests and are not packaged with the runtime module.

Single test entrypoint:

```bash
cd docktap

# Full suite
python test_suite.py all

# Targeted scenarios
python test_suite.py lifecycle
python test_suite.py parallel-images
python test_suite.py mixed --clients 5
python test_suite.py session
```

## Key Files

- `stream_test.py`: launcher used by test suite (starts `DockerProxyServer`)
- `main.py`: sidecar bootstrap path
- `proxy/docker_proxy.py`: proxy server abstraction
- `proxy/operation_log.py`: operation model, parsing, tracking, JSON logging
- `test_suite.py`: unified test harness

