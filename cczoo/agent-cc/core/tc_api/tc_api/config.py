# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from decouple import config

# Server Configuration
HOST = config("HOST", default="0.0.0.0")
PORT = config("PORT", default=8000, cast=int)
DEBUG = config("DEBUG", default=False, cast=bool)
LOG_LEVEL = config("LOG_LEVEL", default="DEBUG" if DEBUG else "INFO")

# Docker Configuration
DOCKER_REGISTRY = config("DOCKER_REGISTRY", default="docker.io")
DOCKER_REPOSITORY = config("DOCKER_REPOSITORY", default="<<your docker hub account>>")

# File Storage Configuration
UPLOAD_DIR = config("UPLOAD_DIR", default="./uploads")
BUILD_DIR = config("BUILD_DIR", default="./builds")
LOGS_DIR = config("LOGS_DIR", default="./logs")
LUKS_VFS_BASE_DIR = config("LUKS_VFS_BASE_DIR", default="./luks/vfs")
LUKS_MOUNT_BASE_DIR = config("LUKS_MOUNT_BASE_DIR", default="./builds/luks")
BUILD_PACKAGE_MAX_REQUEST_BYTES = config("BUILD_PACKAGE_MAX_REQUEST_BYTES", default=33554432, cast=int)
ALLOWED_EXTERNAL_IMAGE_REGISTRIES = config(
	"ALLOWED_EXTERNAL_IMAGE_REGISTRIES",
	default="docker.io,localhost,127.0.0.1",
)
COMMIT_QUEUE_DB = config("COMMIT_QUEUE_DB", default="/dev/shm/commit_queue.db")
OWNER_KEY_DIR = config("OWNER_KEY_DIR", default="./logs/owner_keys")

# External Tools
DOCKER_CMD = config("DOCKER_CMD", default="docker")
COSIGN_CMD = config("COSIGN_CMD", default="cosign")
SYFT_CMD = config("SYFT_CMD", default="syft")
SKOPEO_CMD = config("SKOPEO_CMD", default="skopeo")
SKOPEO_SOURCE = config("SKOPEO_SOURCE", default="docker-daemon")
SKOPEO_DESTINATION = config("SKOPEO_DESTINATION", default="oci")

# KBS Configuration
KBS_URL = config("KBS_URL", default="http://127.0.0.1:8006/cdh/resource/default/image-decryption-keys/")
KBS_ENDPOINT = config("KBS_ENDPOINT", default="/kbs/v0")
KBS_CLIENT_CMD = config("KBS_CLIENT_CMD", default="kbs-client")
KBS_FETCH_RETRIES = config("KBS_FETCH_RETRIES", default=5, cast=int)
KBS_FETCH_RETRY_DELAY_SECONDS = config("KBS_FETCH_RETRY_DELAY_SECONDS", default=1.0, cast=float)

# Sigstore author Configuration
GIT_EMAIL = config("GIT_EMAIL", default="<your sigstore email>")

# Runtime feature flags
INIT_DEFAULT_CHAIN_ON_STARTUP = config("INIT_DEFAULT_CHAIN_ON_STARTUP", default=True, cast=bool)
DEFAULT_MEASURED_CHAIN_ID = "default"
TRANSPARENCY_SERVICE_CHAIN_ID = DEFAULT_MEASURED_CHAIN_ID
TRANSPARENCY_WORKLOAD_CHAIN_PREFIX = ""

# Trust API Configuration
TRUCON_URL = config("TRUCON_URL", default="http://127.0.0.1:8001")
TRUCON_UDS_PATH = config("TRUCON_UDS_PATH", default="")

# TruCon Service Authentication
TRUCON_SERVICE_TOKEN = config("TRUCON_SERVICE_TOKEN", default="")
TRUCON_AUTH_DISABLED = config("TRUCON_AUTH_DISABLED", default=False, cast=bool)

