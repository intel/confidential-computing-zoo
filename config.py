from decouple import config

# Server Configuration
HOST = config("HOST", default="0.0.0.0")
PORT = config("PORT", default=8000, cast=int)
DEBUG = config("DEBUG", default=False, cast=bool)

# Docker Configuration
DOCKER_REGISTRY = config("DOCKER_REGISTRY", default="docker.io")
DOCKER_REPOSITORY = config("DOCKER_REPOSITORY", default="myrepo")

# File Storage Configuration
UPLOAD_DIR = config("UPLOAD_DIR", default="./uploads")
BUILD_DIR = config("BUILD_DIR", default="./builds")
LOGS_DIR = config("LOGS_DIR", default="./logs")

# External Tools
DOCKER_CMD = config("DOCKER_CMD", default="docker")
COSIGN_CMD = config("COSIGN_CMD", default="cosign")
SYFT_CMD = config("SYFT_CMD", default="syft")
SKOPEO_CMD = config("SKOPEO_CMD", default="skopeo")

# KBS Configuration
KBS_ENDPOINT = config("KBS_ENDPOINT", default="http://localhost:8080")
KBS_CLIENT_CMD = config("KBS_CLIENT_CMD", default="kbs-client")
