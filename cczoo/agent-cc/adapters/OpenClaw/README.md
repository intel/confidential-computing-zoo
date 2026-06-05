# OpenClaw Adapter

This directory is the Agent-CC adapter entry point for OpenClaw.

It represents the deployment-side integration path for running OpenClaw inside the Agent-CC model without requiring invasive framework changes. The adapter is intended to consume the shared core services from `core/` rather than reimplementing trust, build, or attestation flows locally.

## Current Scope

- Use OpenClaw as the reference agent workload for Agent-CC end-to-end validation.
- Connect OpenClaw runtime deployment to the shared TC-API build, launch, and verification path.
- Reuse shared trust infrastructure such as trusted logging, attestation-gated secret release, and encrypted storage helpers.

## Related Core Services

- [`../../core/tc-api/`](../../core/tc-api/) for trusted build, publish, launch, and verification orchestration
- [`../../core/tlog/`](../../core/tlog/) for immutable signed runtime evidence and digest rules
- [`../../core/trust-service/`](../../core/trust-service/) for attestation support services used by the deployment flow

## Status

This adapter currently serves as a documentation and integration entry point. Concrete OpenClaw-specific deployment assets will be added here as the adapter path is expanded.

## Start Here

1. Read [`../../README.md`](../../README.md) for the top-level Agent-CC architecture and end-to-end scenario.
2. Read [`../../core/tc-api/README.md`](../../core/tc-api/README.md) for the trusted build-to-runtime control path.
3. Read [`../../core/trust-service/README.md`](../../core/trust-service/README.md) if you need the attestation service container setup.

## Deployment Walkthrough

The example below keeps OpenClaw as the workload being built and deployed, but reuses the shared TC-API, TLog, and trust-service stack from `core/`.

Use this README when you want the OpenClaw-specific operator path. Keep [`../../core/tc-api/README.md`](../../core/tc-api/README.md) as the source of truth for the full API surface, testing entrypoints, and runtime configuration.

### Prerequisites

- A TDX-capable guest with `/dev/tdx_guest` and quote generation available
- Docker, Skopeo, Syft, and Cosign installed on the deployment host
- A Docker registry account for publishing encrypted images
- A Sigstore-capable identity for OIDC login flows
- Reachable trust-service and KBS dependencies for attested launch flows

### Local Environment Setup

```bash
cd <workdir>
git clone --branch dev/v1.5 https://github.com/intel/confidential-computing-zoo.git

python3 -m venv tcapi_env
source tcapi_env/bin/activate

cd confidential-computing-zoo/cczoo/agent-cc/core/tc-api/
pip install -r requirements.txt

# Set registry and Sigstore identity settings.
vim .env
# DOCKER_REGISTRY=docker.io
# DOCKER_REPOSITORY=<your docker hub account>
# GIT_EMAIL=<your sigstore email>

docker login -u <DOCKER_REPOSITORY>
export DOCKER_BUILDKIT=1

bash setup.sh

cd ../tlog
python -m pip install -e .
python -m pip install -e '.[rekor]'
```

### Start Trust Services

The OpenClaw example assumes the trust-service container and a local KBS are available before TC-API starts.

Start trust-service from [`../../core/trust-service/`](../../core/trust-service/):

```bash
cd <workdir>
mkdir -p certs

openssl genrsa -out certs/cosign.pem
openssl rsa -in certs/cosign.pem -pubout -out certs/cosign.pub
openssl genrsa -out certs/openssl.pem
openssl rsa -in certs/openssl.pem -pubout -out certs/openssl.pub
openssl genrsa -out certs/luks-key

cd confidential-computing-zoo/cczoo/agent-cc/core/trust-service/
docker build -t <trust-service-image> .
docker run -it --network host --privileged \
	-v /var/run/docker.sock:/var/run/docker.sock \
	-v /dev/tdx_guest:/dev/tdx_guest \
	-v /etc/tdx-attest.conf:/etc/tdx-attest.conf \
	-v /etc/sgx_default_qcnl.conf:/etc/sgx_default_qcnl.conf \
	-v /etc/hosts:/etc/hosts \
	-v /sys/kernel/config:/sys/kernel/config \
	-p 8006:8006 \
	<trust-service-image>
```

Start a local KBS:

```bash
cd <workdir>
mkdir -p kbs
cd kbs

openssl genpkey -algorithm ed25519 -out kbs-auth-key.pem
openssl pkey -in kbs-auth-key.pem -pubout -out kbs-auth-pub.pem

cat > kbs-config.toml <<'EOF'
[http_server]
sockets = ["0.0.0.0:8080"]
insecure_http = true

[attestation_token]
insecure_key = true

[attestation_service]
type = "coco_as_builtin"
work_dir = "/opt/confidential-containers/attestation-service"

[attestation_service.attestation_token_broker]
type = "Ear"
duration_min = 5

[attestation_service.rvps_config]
type = "BuiltIn"

[admin]
auth_public_key = "/opt/confidential-containers/kbs/user-keys/kbs-auth-pub.pem"

[[plugins]]
name = "resource"
type = "LocalFs"
dir_path = "/opt/confidential-containers/kbs/repository"
EOF

cd ..
docker run -d -p 8080:8080 --network host \
	-v $(pwd)/kbs/kbs-config.toml:/etc/kbs/kbs-config.toml \
	-v /etc/sgx_default_qcnl.conf:/etc/sgx_default_qcnl.conf \
	-v /etc/hosts:/etc/hosts \
	-v $(pwd)/certs:/opt/confidential-containers/kbs/repository/default/image-decryption-keys \
	-v $(pwd)/kbs/kbs-auth-pub.pem:/opt/confidential-containers/kbs/user-keys/kbs-auth-pub.pem \
	ghcr.io/confidential-containers/staged-images/kbs:c96dbe6bcc3d7529fdb27afb19a54a6625b29634 \
	/usr/local/bin/kbs --config-file /etc/kbs/kbs-config.toml
```

### Start TC-API

For the OpenClaw walkthrough, start the shared control plane from [`../../core/tc-api/`](../../core/tc-api/):

```bash
cd <workdir>/confidential-computing-zoo/cczoo/agent-cc/core/tc-api/
./start.sh restart --reset-state dev
```

If you prefer running the service in a container, build [`../../core/tc-api/Dockerfile`](../../core/tc-api/Dockerfile) and expose the same host sockets and attestation devices described above.

### OpenClaw Build, Publish, and Launch Flow

The shared TC-API flow below is the path OpenClaw is expected to use.

1. Create an encrypted workspace with `POST /api/create_luks` if you want build material, generated artifacts, and deployment data isolated under LUKS.
2. Mount the encrypted workspace with `POST /api/mount_luks` before uploading Dockerfiles, binaries, configs, or data for the OpenClaw image.
3. Submit the OpenClaw image build through `POST /api/build-package`.
4. Publish the encrypted image and SBOM through `POST /api/publish-package`.
5. Launch the workload with attestation enabled through `POST /api/deploy-launch`.
6. Verify evidence by querying the build, publish, launch, and transparency-log result endpoints.

Example CLI calls:

```bash
# Create and mount an encrypted workspace.
venv/bin/python -m tc_api.cli.client --base-url http://localhost:8000 --sigstore-login oob \
	create_luks --payload-json '{"user_id":"<sigstore account>","vfs_path":"<luks file>","vfs_size":"<size>","passwd":"<luks key file>"}'

venv/bin/python -m tc_api.cli.client --base-url http://localhost:8000 --sigstore-login oob \
	mount_luks --payload-json '{"user_id":"<sigstore account>","vfs_path":"<luks file>","vfs_size":"<size>","mapper_dir":"<mapper>","loop_device":"<loop>","mount_path":"<mount path>","passwd":"<luks key file>"}'

# Build the OpenClaw image from artifacts staged in the mounted workspace.
venv/bin/python -m tc_api.cli.client --base-url http://localhost:8000 --sigstore-login oob \
	build --payload-json '{"dockerfile":"<path or content>","app_binary":"<openclaw artifact>","configs":["<config file>"],"data":["<data file>"],"encrypt":true,"user_id":"<sigstore account>","luks_path":"<mounted luks path>"}'

# Publish the encrypted image.
venv/bin/python -m tc_api.cli.client --base-url http://localhost:8000 --sigstore-login oob \
	publish --payload-json '{"build_id":"<build_id>","image_id":"<image_id>","user_id":"<sigstore account>","sbom_url":"<sbom path>","log_evidence":true,"luks_path":"<mounted luks path>"}'

# Launch the attested OpenClaw workload.
curl -X POST http://localhost:8000/api/deploy-launch \
	-H 'Content-Type: application/json' \
	-d '{"image_id":"tc-api-build-<build_id>","build_id":"<build_id>","user_id":"<sigstore account>","image_url":"docker.io/<repo>/tc-api-build-<build_id>:latest-encrypted","sbom_url":"<sbom path>","attestation_required":true,"luks_path":"<mounted luks path>","dockercmd":"<optional openclaw docker run command>"}'
```

### Result Inspection

After each phase, inspect the corresponding result object and trust evidence:

- `GET /api/build-result/{build_id}` for image URLs, SBOM paths, and build trust status
- `GET /api/publish-result/{build_id}` for registry publication details
- `GET /api/launch-result/{launch_id}` for attestation result, workload instance IDs, and launch evidence
- `GET /api/transparency-log/{log_id}` for the concrete immutable log entry
- `POST /api/get-summaryTransparencylog` for a single summary over build, publish, and launch log records

The full payload shapes and additional operator notes remain in [`../../core/tc-api/README.md`](../../core/tc-api/README.md).
