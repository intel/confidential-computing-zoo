# Test Tools for docktap proxy

Test scripts are consolidated into a single entry point:

- `../test_suite.py`

## Quick Start

```bash
cd docktap

# Run everything
python test_suite.py all

# Run a single scenario
python test_suite.py lifecycle
python test_suite.py mixed --clients 5
python test_suite.py multi-container --containers 3 --multi-image nginx
```

## Modes

- `all`
- `docker-direct`
- `concurrent-same`
- `parallel-images`
- `create-parallel`
- `lifecycle`
- `multi-container`
- `mixed`
- `session`

