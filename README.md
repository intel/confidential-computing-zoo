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

## Testing

Use the single entrypoint for tests:

```shell
python -m tests.test_runner --type all
```

Common options:

```shell
python -m tests.test_runner --type unit
python -m tests.test_runner --type manual --name health
```

## Operational Notes

- TruCon is the sole supported trust-event path. The legacy direct trusted-log write path has been retired and is not a valid rollback target.
- Recommended rollout posture is TruCon-only operation with process supervision, parity checks on critical flows, and degraded-mode handling that preserves external business results when trust-event submission is unavailable.
- Docktap keeps only bounded local routing, mapping, and retry state. Replay and verification rely on TruCon and immutable backend state rather than Docktap-local persistence.

## API Endpoints

### 1. Build and Package
`POST /api/build-package`

Submit container build requests with Dockerfile, application binary, configs, and optional signing/encryption.

***Quick Check***
```shell
curl -X POST "http://localhost:8000/api/build-package" -H "Content-Type:application/json" -d '{"dockerfile":"FROM python:3.9-slim\nWORKDIR .\nCOPY . .","app_binary":"dGVzdCBiaW5hcnkK","configs":["Y29uZmlnCg=="],"data":["ZGF0YQo="],"encrypt":true,"user_id":"test-user"}'
```

**Request Body:**
```json
{
  "dockerfile": "<file>",
  "app_binary": "<file>", // Optional
  "configs": ["file1", "file2"],  // Optional
  "data": ["file3"],  // Optional
  "sign_key": "<private_key.pem>", // Optional
  "cert": "<cert.pem>",  // Optional
  "encrypt": true, 
  "user_id": "test-user"
}
```

**Response:**
```json
{
  "build_id": "bld-xxx",
  "status": "", // build image status
  "estimated_time": "timestamp", 
  "user_id": "user_id",
  "transparencyLog_verify": ""
}
```

### 2. Query Build Result 
`GET /api/build-result/{build_id}`

Query build status and results including image ID, SBOM URL and certificates.

***Quick Check***
```shell
curl  "http://localhost:8000/api/build-result/{build_id}"
```

**Response:**
```json
{
  "user_id":"test-user",
  "build_id":"{build_id}",
  "status":"success",
  "current_step":"Build completed successfully",
  "image_id":"oci:./builds/{build_id}/test-{build_id}",
  "sbom_url":"./builds/{build_id}/user-{build_id}-sbom.json",
  "image_url":"./builds/{build_id}/user-{build_id}",
  "cert_url":"/api/artifacts/{build_id}/cosign.crt",
  "log_id":"xxxxxxx",
  "transparencyLog_verify":"success",
  "error_message":null,
  "created_at":"<timestamp>",
  "updated_at":"<timestamp>"
}
```

### 3. Publish Package
`POST /api/publish-package`

Publish built image and SBOM with key management and evidence logging.

***Quick Check***
```shell
curl  curl -X POST "http://localhost:8000/api/publish-package" -H "Content-Type:application/json" -d '{"build_id":"{build_id}","image_id":"{image_id}","user_id":"{user_id}","sbom_url":"{sbom_url}","log_evidence":true}'
```

**Request:**
```json

  {
    "build_id":"{build_id}",
    "status":"success",
    "image_url":"docker.io/{docker_account}/test-{build_id}:latest-encrypted", // Optional
    "user_id":"{user_id}",
    "image_id":"test-{build_id}",
    "sbom_url":"./builds/{build_id}/{build_id}-sbom.json",
    "log_evidence":"True"
  }
```

**Response:**
```json
  {
    "build_id":"{build_id}",
    "status":"success",
    "image_url":"docker.io/trustedzoo/test-{build_id}:latest-encrypted",
    "user_id":"test-user",
    "image_id":"test-{build_id}",
    "sbom_url":"./builds/{build_id}/{build_id}-sbom.json",
    "log_id":"xxxxxxxxx",
    "transparencyLog_verify":"success",
    "published_at":"<timestamp>"
  }
```

### 4. Query Publish Result
`GET /api/publish-result/{build_id}`

Query publish status and results including image ID, SBOM URL ...

***Quick Check***
```shell
curl  "http://localhost:8000/api/publish-result/{build_id}"
```

**Response:**
```json
{
  "user_id":"test-user",
  "build_id":"{build_id}",
  "status":"success",
  "current_step":"Build completed successfully",
  "image_id":"oci:./builds/{build_id}/user-{build_id}",
  "sbom_url":"./builds/{build_id}/user-{build_id}-sbom.json",
  "image_url":"./builds/{build_id}/user-{build_id}",
  "cert_url":"/api/artifacts/{build_id}/cosign.crt",
  "log_id":"xxxxxxx",
  "transparencyLog_verify":"success",
  "error_message":null,
  "created_at":"<timestamp>",
  "updated_at":"<timestamp>"
}
```


### 5. Deploy Launch
`POST /api/deploy-launch`

Launch container with attestation and secure deployment.

***Quick Check***
```shell
curl -X POST "http://localhost:8000/api/deploy-launch" -H "Content-Type:application/json" -d '{"image_id":"test-{build_id}","build_id": "{build_id}","user_id":"test-user","image_url":"docker.io/{docker_account}/test-{build_id}:latest-encrypted","sbom_url":null,"attestation_required":true}'
```

**Request:**
```json
{
  "image_id":"test-{build_id}",
  "build_id": "{build_id}",
  "user_id":"test-user",
  "image_url":"docker.io/{docker_account}/test-{build_id}:latest-encrypted", // Optional
  "sbom_url":null,  // Optional
  "attestation_required":true
}
```

**Response:**
```json
{
  "launch_id":"launch-xxxxxxx",
  "status":"initiated",
  "user_id":"test-user",
  "log_id":null,
  "transparencyLog_verify":null,
  "created_at":"<timestamp>"
}
```

### 6. Query Launch Result
`GET /api/launch-result/{launch_id}`

Query launch status and attestation results.

***Quick Check***
```shell
curl "http://localhost:8000/api/launch-result/{launch_id}"

```
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

### 7. Query transparency log
`GET /api/transparency-log/{log_id}`

Query transparency status including transparency log content, build_id and log_id.

***Quick Check***
```shell
curl  "http://localhost:8000/api/transparency-log/{log_id}"

```
**Response:**
```json
  {
    "user_id":"test-user",
    "build_id":"bld-xxxxxx",
    "log_id":"xxxxxxxxx",
    "status":"added",
    "transparency_log":"<log content>",
    "transparencyLog_verify":null,
    "error_message":null
  }
```

### 8. Query all taransparency log
`POST /api/get-summaryTransparencylog`

Query all transparency log.

***Quick Check***
```shell
curl "http://localhost:8000/api/get-summaryTransparencylog" -H "Content-Type:application/json" -d '{"build_id":"{build_id}","launch_id":"{launch_id}"}'

```
**Response:**
```json
{
  "build_id":"{build_id}",
  "launch_id":"{launch_id}",
  "log_id":{
    "build":"xxxxxxxxx",
    "publish":"xxxxxxxxx",
    "launch":"xxxxxxxxx"
    },
  "transparencylog":{
    "build":"<build transparency log coentent>",
    "publish":"<publish transparency log coentent>",
    "launch":"<launch transparency log coentent>"
  }
}
```

## Quick Start

### Set Up Environment

Before running the tests, make sure you have configured your Docker Hub (`docker.io`) account.  
Otherwise, tests involving image build, push, and deployment will fail.

#### Configure docker.io account
1. Log in using the CLI:

```bash
   docker login docker.io
```
or
```bash
   skopeo login docker.io
```
Enter your Docker Hub username and password (or Personal Access Token).

2. Verify login:

```bash
   docker info
```
This should show your username under "Username" and confirm you are logged in.

3. For CI/CD environments, you can pass credentials via environment variables:

```bash
export DOCKER_USERNAME=<your-username>
export DOCKER_PASSWORD=<your-password-or-token>
echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin docker.io
```
Please note, you need to update DOCKER_REPOSITORY in `config.py` to your Docker Hub repository name before running the tests.

### Install Dependencies and use python virtual env(python is already installed)

1. Create & active virtual environment

```bash
python -m venv {env-name}
source {env-name}/bin/activate
```

2. Install dependencies

```bash
cd tc_api
pip install -e .
```

3. Start ASR && AA && CDH && KBS

Please refer to: [https://github.com/RodgerZhu/deploy-encrypted-image-in-tdvm?tab=readme-ov-file](https://github.com/RodgerZhu/deploy-encrypted-image-in-tdvm?tab=readme-ov-file).

### Run Service

```bash
python -m tc_api.main
```

The service will start at http://localhost:8000.

### Deploy with Docker

### Build image & start service in container
1. Build tc_api image

```bash
# Non-TDX build (default)
docker build --build-arg ENABLE_TDX=false -t {image_name:image_tag} .

# TDX build (requires TDX libs in build context)
docker build --build-arg ENABLE_TDX=true -t {image_name:image_tag} .

# Build with external proxy configuration
docker build \
  --build-arg ENABLE_TDX=false \
  --build-arg http_proxy=$http_proxy \
  --build-arg https_proxy=$https_proxy \
  --build-arg no_proxy=$no_proxy \
  --build-arg HTTP_PROXY=$HTTP_PROXY \
  --build-arg HTTPS_PROXY=$HTTPS_PROXY \
  --build-arg NO_PROXY=$NO_PROXY \
  -t {image_name:image_tag} .

# Run container
docker run -it --network host --privileged \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -p 8001:8001 -p 8006:8006 -p 8000:8000 \
  {image_name:image_tag}

# If running with TDX mode, add TDX mounts and env
docker run -it --network host --privileged \
  -e ENABLE_TDX=true \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /dev/tdx_guest:/dev/tdx_guest \
  -v /etc/tdx-attest.conf:/etc/tdx-attest.conf \
  -p 8001:8001 -p 8006:8006 -p 8000:8000 \
  {image_name:image_tag}
```

##### Notice: Check the port in Dockerfile to ensure the ports are not in use. 

### Deploy with Docker Compose

Docker Compose deploys three services: `tc-api`, `trucon`, and `docktap`.

1. Generate a service token and start all services:

```bash
# Generate shared service token
export TRUCON_SERVICE_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "TRUCON_SERVICE_TOKEN=$TRUCON_SERVICE_TOKEN" >> .env

# Create Docktap proxy socket directory on host
sudo mkdir -p /var/run/docktap

# Start all services
docker compose up -d
```

2. Configure Docker CLI to route through Docktap proxy:

```bash
export DOCKER_HOST=unix:///var/run/docktap/docker.sock
```

To make this permanent for all users on the TD VM:

```bash
echo 'export DOCKER_HOST=unix:///var/run/docktap/docker.sock' | sudo tee /etc/profile.d/docktap.sh
sudo chmod +x /etc/profile.d/docktap.sh
```

3. Verify all services are healthy:

```bash
docker compose ps
curl http://localhost:8000/        # tc-api health
curl http://localhost:8001/status   # trucon status
curl http://localhost:8002/healthz  # docktap health
```

### Docktap Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TRUCON_URL` | `http://127.0.0.1:8001` | TruCon endpoint for event submission |
| `TRUCON_SERVICE_TOKEN` | (generated) | Shared Bearer token for TruCon auth |
| `SOCK_BRIDGE_SOCKET` | `/tmp/docker-proxy.sock` | Proxy socket listen path |
| `DOCKER_SOCKET` | `/var/run/docker.sock` | Docker daemon socket path |
| `DOCKTAP_HEALTH_PORT` | `8002` | HTTP health endpoint port |
| `DOCKTAP_SOCKET` | `/var/run/docktap/docker.sock` | Proxy socket path (bare-metal `start.sh`) |

## Configuration

Configure via environment variables:

- `HOST`: Service listening address (default: 0.0.0.0)
- `PORT`: Service port (default: 8000)
- `DOCKER_REGISTRY`: Docker image registry address
- `ENABLE_TDX`: enable TDX-specific flow and mounts (`true` or `false`, default `false`)
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
├── src/
│   └── tc_api/       # Application package
│       ├── main.py       # FastAPI application main file
│       ├── trucon.py     # TruCon sequencer service
│       ├── models.py     # Pydantic data models
│       ├── services.py   # Docker related services
│       ├── kbs_service.py# KBS client service
│       ├── config.py     # Configuration file
│       └── trusted_container_log/
├── tests/            # Test suites and test runner
├── scripts/          # VFS, platform, and container helper scripts
├── deploy/           # Deployment-specific assets such as nginx config
├── docs/             # System and component architecture docs
├── pyproject.toml    # Packaging and src-layout configuration
├── requirements.txt  # Python dependencies
├── Dockerfile        # Docker build file
└── README.md         # Project documentation
```

## Testing

The project includes comprehensive test suites for all API endpoints.

### Test Files

- `tests/test_api.py` - Manual integration tests with detailed output
- `tests/test_unit.py` - Automated unit and integration tests using pytest
- `docs/TESTING.md` - Detailed testing documentation

### Quick Test Commands

```bash
# Run all tests through a single entrypoint
python -m tests.test_runner --type all

# Run deterministic unit coverage
python -m tests.test_runner --type unit --no-service-management --verbose

# Run specific manual test
python -m tests.test_runner --type manual --name health

# Manual test against a non-default endpoint
TC_API_BASE_URL=http://localhost:18000 python -m tests.test_runner --type manual --name health

# Wait up to 90s for manual endpoint readiness
python -m tests.test_runner --type manual --name health --base-url http://localhost:18000 --manual-ready-timeout 90

# Backward-compatible wrappers
./run_tests.sh --type all --verbose
./scripts/run_tests.ps1 --type unit --verbose
```

See `docs/TESTING.md` for complete testing documentation and `docs/architecture.md` for system design.

Docktap-specific design details are in `docs/docktap/architecture.md`.
