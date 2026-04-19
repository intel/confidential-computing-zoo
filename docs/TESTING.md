# TC API Testing Guide

This document explains how to run the test suite for the TC API service.

## Test Files

- `tests/test_api.py` - Manual integration tests with detailed output
- `tests/test_unit.py` - Automated unit and integration tests using pytest
- `tests/test_subprocess_unit.py` - Deterministic subprocess-mocked Docker/non-Docker unit coverage
- `tests/test_runner.py` - Single test entrypoint for all test types

## Prerequisites

1. Install dependencies:
```bash
pip install -e .
```

2. Start the TC API service (required for manual/integration tests):
```bash
python -m tc_api.main
```

The service should be running on `http://localhost:8000`

## Running Tests

Use a single entrypoint for all test flows:

```bash
python -m tests.test_runner --type all
```

### Test types

```bash
python -m tests.test_runner --type manual
python -m tests.test_runner --type unit
python -m tests.test_runner --type integration
python -m tests.test_runner --type performance
```

`--type unit` runs deterministic subprocess-focused coverage in `tests/test_subprocess_unit.py`.

### Useful options

```bash
python -m tests.test_runner --type manual --name health
python -m tests.test_runner --type all --verbose
python -m tests.test_runner --type all --stop-on-fail
python -m tests.test_runner --type unit --no-service-management
python -m tests.test_runner --type manual --name health --base-url http://localhost:18000 --manual-ready-timeout 90
```

Manual tests can target a non-default endpoint:

```bash
TC_API_BASE_URL=http://localhost:18000 python -m tests.test_runner --type manual --name health
```

Backward-compatible wrappers still work:

```bash
bash run_tests.sh --type all
```

## Verification CLI Checks

The operator-facing chain verification CLI can be exercised directly:

```bash
tc-verify --evidence evidence.json
tc-verify --evidence evidence.json --json
tc-verify default
tc-verify default --json
tc-verify default --signer-identity alice@example.com
tc-verify default --expected-entry-count 12
tc-verify default --fail-on-pending
tc-verify default --require-tee
```

Recommended targeted regression for the verification plane:

```bash
/home/siyuan/tc_api/.venv/bin/python -m pytest tests/test_tlog_impl.py tests/test_non_tee_verification.py tests/test_verify_cli.py -q
```

`--require-tee` should fail when TruCon reports non-TEE fallback mode. Non-TEE verification remains suitable for development and test environments only.

Prefer exported evidence as the primary operator input. Using `tc-verify <chain_id>` without `--evidence` is a transitional live TruCon fallback path for tightly coupled deployments and troubleshooting.

## Test Coverage

### API Endpoints Tested

1. **Health Check** (`GET /`)
   - ✅ Service availability
   - ✅ Response format validation

2. **Build Package** (`POST /api/build-package`)
   - ✅ Successful build submission
   - ✅ Build with encryption enabled
   - ✅ Invalid data validation
   - ✅ Build ID generation

3. **Build Result** (`GET /api/build-result/{build_id}`)
   - ✅ Successful result retrieval
   - ✅ Non-existent build handling
   - ✅ Status progression tracking

4. **Publish Package** (`PUT /api/publish-package`)
   - ✅ Successful image publishing
   - ✅ SBOM handling
   - ✅ Metadata processing

5. **Register Key** (`POST /api/keys/register`)
   - ✅ Successful key registration
   - ✅ Policy validation
   - ✅ Invalid data handling

6. **Get Artifact** (`GET /api/artifacts/{build_id}/{artifact_type}`)
   - ✅ Artifact retrieval
   - ✅ Non-existent artifact handling

### Test Types

- **Unit Tests**: Individual API endpoint functionality
- **Integration Tests**: Complete workflow testing
- **Performance Tests**: Concurrent request handling
- **Validation Tests**: Input validation and error handling

## Sample Test Data

The tests use sample data including:
- Mock Dockerfile for nginx-based container
- Sample private/public key pairs (for testing only)
- Sample certificates
- Mock SBOM data

## Expected Behavior

### Successful Test Run Output

```
TC API Comprehensive Test Suite
============================================================
Testing health check...
Status: 200
Response: {'message': 'TC API Service is running', 'timestamp': '...'}
--------------------------------------------------
Testing build package...
Status: 200
Build ID: bld-1234567890
Status: submitted
Estimated Time: 120s
--------------------------------------------------
...
============================================================
All tests completed successfully!
```

### Common Issues

1. **Connection Error**: Make sure the TC API service is running
2. **Build Failures**: Check that Docker tools are available (for actual implementation)
3. **Validation Errors**: Verify request payload format matches API schema

## Continuous Integration

To run tests in CI/CD pipeline:

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
python -m tests.test_runner --type all --verbose
```

## Test Development

To add new tests:

1. For manual tests: Add functions to `tests/test_api.py`
2. For automated tests: Add methods to appropriate class in `tests/test_unit.py`
3. Use descriptive test names and include docstrings
4. Test both success and failure scenarios
5. Clean up any resources created during tests

## Mocking External Dependencies

The current implementation uses mock responses for external tools:
- Docker commands are simulated
- Cosign signing is mocked
- Syft SBOM generation is simulated
- KBS service calls are mocked

For production testing, consider using actual tool integrations or more sophisticated mocking.
