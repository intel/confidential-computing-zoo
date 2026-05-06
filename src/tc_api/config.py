from decouple import config

# Server Configuration
HOST = config("HOST", default="0.0.0.0")
PORT = config("PORT", default=8000, cast=int)
DEBUG = config("DEBUG", default=False, cast=bool)

# Docker Configuration
DOCKER_REGISTRY = config("DOCKER_REGISTRY", default="docker.io")
DOCKER_REPOSITORY = config("DOCKER_REPOSITORY", default="trustedzoo")

# File Storage Configuration
UPLOAD_DIR = config("UPLOAD_DIR", default="./uploads")
BUILD_DIR = config("BUILD_DIR", default="./builds")
LOGS_DIR = config("LOGS_DIR", default="./logs")
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
GIT_EMAIL = config("GIT_EMAIL", default="qingchengx.zeng@intel.com")

# Runtime feature flags
ENABLE_TDX = config("ENABLE_TDX", default=True, cast=bool)
INIT_DEFAULT_CHAIN_ON_STARTUP = config("INIT_DEFAULT_CHAIN_ON_STARTUP", default=True, cast=bool)
TRANSPARENCY_SERVICE_CHAIN_ID = config("TRANSPARENCY_SERVICE_CHAIN_ID", default="tc-api-service")
TRANSPARENCY_WORKLOAD_CHAIN_PREFIX = config("TRANSPARENCY_WORKLOAD_CHAIN_PREFIX", default="tc-api-workload-")

# Trust API Configuration
TRUCON_URL = config("TRUCON_URL", default="http://127.0.0.1:8001")
TRUCON_UDS_PATH = config("TRUCON_UDS_PATH", default="")

# TruCon Service Authentication
TRUCON_SERVICE_TOKEN = config("TRUCON_SERVICE_TOKEN", default="")
TRUCON_AUTH_DISABLED = config("TRUCON_AUTH_DISABLED", default=False, cast=bool)

