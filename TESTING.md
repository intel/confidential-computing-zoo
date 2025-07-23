# TC API Testing Guide

This document explains how to run the test suite for the TC API service.

## Test Files

- `test_api.py` - Manual integration tests with detailed output
- `test_unit.py` - Automated unit and integration tests using pytest

## Prerequisites

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start the TC API service:
```bash
python main.py
```

The service should be running on `http://localhost:8000`

## Running Tests

### 1. Manual Integration Tests (`test_api.py`)

Run all tests:
```bash
python test_api.py
```

Run a specific test:
```bash
python test_api.py health    # Health check only
python test_api.py build     # Build package only
python test_api.py publish   # Publish package only
python test_api.py register  # Register key only
```

### 2. Automated Unit Tests (`test_unit.py`)

Run all tests with pytest:
```bash
pytest test_unit.py -v
```

Run specific test classes:
```bash
pytest test_unit.py::TestTCAPI -v                # API endpoint tests
pytest test_unit.py::TestIntegration -v          # Integration tests
pytest test_unit.py::TestPerformance -v          # Performance tests
```

Run specific test methods:
```bash
pytest test_unit.py::TestTCAPI::test_health_check -v
pytest test_unit.py::TestTCAPI::test_build_package_success -v
```

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

# Start service in background
python main.py &
SERVICE_PID=$!

# Wait for service to start
sleep 5

# Run tests
pytest test_unit.py -v --tb=short

# Stop service
kill $SERVICE_PID
```

## Test Development

To add new tests:

1. For manual tests: Add functions to `test_api.py`
2. For automated tests: Add methods to appropriate class in `test_unit.py`
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
