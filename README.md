# TC API - Trusted Container Build and Publish Service

A RESTful API service framework built with Python and FastAPI for handling Docker image building, publishing, signing, and encryption workflows.

## Features

- **Container Image Building**: Support building custom images via uploaded Dockerfile
- **SBOM Generation**: Automatically generate SPDX JSON format Software Bill of Materials using Syft
- **Image Encryption**: Encrypt images using Skopeo
- **Digital Signing**: Sign images and SBOMs using Cosign
- **Image Publishing**: Support publishing to Docker Hub and other image registries
- **Key Management**: Integrate with KBS (Key Broker Service) for key registration and management

## API Endpoints

### 1. Build and Package Request
`POST /api/build-package`

Submit container image build tasks with support for Dockerfile, signing keys, certificates, and other parameters.

### 2. Publish Image and SBOM  
`PUT /api/publish-package`

Publish built images and SBOMs to image repositories.

### 3. Register Key Metadata
`POST /api/keys/register`

Register key metadata with KBS, including public keys, certificates, and usage policies.

### 4. Query Build Results
`GET /api/build-result/{build_id}`

Query build status and result information by build ID.

## Quick Start

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Service

```bash
python main.py
```

The service will start at http://localhost:8000.

### Deploy with Docker

```bash
# Build image
docker build -t tc-api:latest .

# Run container
docker run -p 8000:8000 tc-api:latest
```

## Configuration

Configure via environment variables:

- `HOST`: Service listening address (default: 0.0.0.0)
- `PORT`: Service port (default: 8000)
- `DOCKER_REGISTRY`: Docker image registry address
- `UPLOAD_DIR`: File upload directory
- `BUILD_DIR`: Build working directory

## Dependencies

The service depends on the following external tools, please ensure they are properly installed:

- Docker
- Cosign
- Syft  
- Skopeo
- KBS Client (optional)

## Project Structure

```
tc_api/
├── main.py           # FastAPI application main file
├── models.py         # Pydantic data models
├── services.py       # Docker related services
├── kbs_service.py    # KBS client service
├── config.py         # Configuration file
├── requirements.txt  # Python dependencies
├── Dockerfile        # Docker build file
└── README.md         # Project documentation
```

## Testing

The project includes comprehensive test suites for all API endpoints.

### Test Files

- `test_api.py` - Manual integration tests with detailed output
- `test_unit.py` - Automated unit and integration tests using pytest
- `TESTING.md` - Detailed testing documentation

### Quick Test Commands

```bash
# Run all tests
python test_api.py

# Run specific manual test
python test_api.py health
python test_api.py build

# Run automated tests
pytest test_unit.py -v

# Use test runner scripts
./run_tests.sh --type all --verbose
.\run_tests.ps1 -TestType unit -Verbose
```

See `TESTING.md` for complete testing documentation.
