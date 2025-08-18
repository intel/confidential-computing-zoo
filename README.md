# TC API - Trusted Container Build and Publish Service

A RESTful API service framework built with Python and FastAPI for handling Docker image building, packing, launching, deploying of applications runtime in a secure and auditable manner.

## Features

- **Container Image Building**: Build and package container images with Dockerfile and application components
- **SBOM Generation**: Generate and sign SPDX format Software Bill of Materials (SBOM) using Syft
- **Image Security**: Support image encryption using Skopeo and digital signing using Cosign
- **Image Publishing**: Publish signed images and SBOMs to container registries with policy management
- **Key Management**: Integrate with KBS for key management and RVPS for verification policies
- **Secure Deployment**: Support secure container launch with remote attestation in CVM
- **Audit Logging**: Record build and deploy evidence in Transparent Log System
- **Runtime Security**: Enable secure container upgrades during runtime

## API Endpoints

### 1. Build and Package
`POST /api/build-package`

Submit container build requests with Dockerfile, application binary, configs, and optional signing/encryption.

**Request Body:**
```json
{
  "dockerfile": "<file>",           
  "app_binary": "<file>",           
  "configs": ["file1", "file2"],   
  "data": ["file3"],                
  "sign_key": "<private_key.pem>",
  "cert": "<cert.pem>",            
  "encrypt": true,               
  "user_id": "user-001"           
}
```

**Response:**
```json
{
  "build_id": "bld-######",       
  "status": "submitted"          
}
```

### 2. Build Result Query
`GET /api/build-result/{build_id}`

Query build status and results including image ID, SBOM URL and certificates.

**Response:**
```json
{
  "build_id": "bld-8de9932",           
  "status": "success",                 
  "image_id": "sha256:abcd1234",        
  "sbom_url": "https://.../sbom.json",  
  "image_url": "docker.io/myrepo/secure-app", 
  "cert_url": "https://.../cert.pem"  
}
```

### 3. Publish Package
`PUT /api/publish-package`

Publish built image and SBOM with key management and evidence logging.

**Request:**
```json
{
  "image_id": "sha256:abcd1234",   
  "user_id": "user-001",          
  "log_evidence": true,        
  "metadata": {
    "tags": ["latest"],             
    "description": "Secure application image"
  }
}
```

**Response:**
```json
{
  "status": "success",                
  "image_url": "docker.io/myrepo/secure-app:latest",
  "sbom_url": "https://.../sbom.json", 
  "log_id": "tx-xxxxxxx"      
}
```

### 4. Deploy Launch
`POST /api/deploy-launch`

Launch container with attestation and secure deployment.

**Request:**
```json
{
  "image_url": "docker.io/secure/app:latest",    
  "image_id": "sha256:abcd1234",              
  "sbom_url": "https://registry.example.com/sbom.json", 
  "user_id": "user-001",                           
  "attestation_required": true                    
}
```

**Response:**
```json
{
  "launch_id": "launch-#######",       
  "status": "initiated"                
}
```

### 5. Launch Result Query
`GET /api/launch-result/{launch_id}`

Query launch status and attestation results.

**Response:**
```json
{
  "launch_id": "launch-######",           
  "status": "success",                     
  "validation": "passed",                  
  "attestation": "trusted",             
  "log_id": "tx-xxxxxxx",              
  "instance_id": [                        
    "inst-#####1",
    "inst-#####2"
  ]
}
```

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
