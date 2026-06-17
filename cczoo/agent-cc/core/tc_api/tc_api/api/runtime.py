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

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..config import (
    BUILD_DIR,
    BUILD_PACKAGE_MAX_REQUEST_BYTES,
    DEFAULT_MEASURED_CHAIN_ID,
    DEBUG,
    DOCKER_REGISTRY,
    DOCKER_REPOSITORY,
    HOST,
    INIT_DEFAULT_CHAIN_ON_STARTUP,
    LUKS_MOUNT_BASE_DIR,
    LUKS_VFS_BASE_DIR,
    LOG_LEVEL,
    LOGS_DIR,
    PORT,
    TRANSPARENCY_SERVICE_CHAIN_ID,
    TRUCON_URL,
    UPLOAD_DIR,
)
from ..services import DockerService


_LOG_LEVEL = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(level=_LOG_LEVEL)
logging.getLogger("tuf.api._payload").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

docker_service = DockerService()


def workload_transparency_chain_id(workload_id: str) -> str:
    return DEFAULT_MEASURED_CHAIN_ID


def has_proxy_configuration() -> bool:
    proxy_keys = (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
    )
    return any(os.environ.get(key) for key in proxy_keys)


def log_proxy_configuration(operation: str) -> None:
    if has_proxy_configuration():
        logger.info("%s using configured proxy environment", operation)
    else:
        logger.info("%s running without proxy environment", operation)


def ensure_runtime_dirs() -> None:
    for directory in [UPLOAD_DIR, BUILD_DIR, LOGS_DIR, LUKS_VFS_BASE_DIR, LUKS_MOUNT_BASE_DIR]:
        os.makedirs(directory, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from tlog.backends.rekor.adapter import SigstoreLogAdapter

    from ..transparency.commit_client import TrustedLogAPI

    app.state.trusted_log = TrustedLogAPI(
        local_mr=None,
        immutable_log=SigstoreLogAdapter(),
        trucon_url=TRUCON_URL,
    )

    if INIT_DEFAULT_CHAIN_ON_STARTUP:
        try:
            app.state.trusted_log.init_chain("default")
        except Exception as exc:
            raise RuntimeError(
                "Default-chain baseline initialization failed during startup. "
                "Provide a reusable Sigstore identity token or disable INIT_DEFAULT_CHAIN_ON_STARTUP. "
                f"Underlying error: {exc}"
            ) from exc

    yield

    logger.info("TC API Service shutting down...")


__all__ = [
    "BUILD_DIR",
    "BUILD_PACKAGE_MAX_REQUEST_BYTES",
    "DEBUG",
    "DOCKER_REGISTRY",
    "DOCKER_REPOSITORY",
    "HOST",
    "INIT_DEFAULT_CHAIN_ON_STARTUP",
    "LUKS_MOUNT_BASE_DIR",
    "LUKS_VFS_BASE_DIR",
    "LOGS_DIR",
    "PORT",
    "DEFAULT_MEASURED_CHAIN_ID",
    "TRANSPARENCY_SERVICE_CHAIN_ID",
    "TRUCON_URL",
    "UPLOAD_DIR",
    "docker_service",
    "ensure_runtime_dirs",
    "has_proxy_configuration",
    "lifespan",
    "log_proxy_configuration",
    "logger",
    "workload_transparency_chain_id",
]