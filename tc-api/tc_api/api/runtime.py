import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..config import (
    BUILD_DIR,
    DEBUG,
    DOCKER_REGISTRY,
    DOCKER_REPOSITORY,
    HOST,
    INIT_DEFAULT_CHAIN_ON_STARTUP,
    LOGS_DIR,
    PORT,
    TRANSPARENCY_SERVICE_CHAIN_ID,
    TRANSPARENCY_WORKLOAD_CHAIN_PREFIX,
    TRUCON_URL,
    UPLOAD_DIR,
)
from ..services import DockerService


logging.basicConfig(level=logging.DEBUG)
logging.getLogger("tuf.api._payload").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

docker_service = DockerService()


def workload_transparency_chain_id(workload_id: str) -> str:
    return f"{TRANSPARENCY_WORKLOAD_CHAIN_PREFIX}{workload_id}"


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
    for directory in [UPLOAD_DIR, BUILD_DIR, LOGS_DIR]:
        os.makedirs(directory, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from tlog_rekor.adapter import SigstoreLogAdapter

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
    "DEBUG",
    "DOCKER_REGISTRY",
    "DOCKER_REPOSITORY",
    "HOST",
    "INIT_DEFAULT_CHAIN_ON_STARTUP",
    "LOGS_DIR",
    "PORT",
    "TRANSPARENCY_SERVICE_CHAIN_ID",
    "TRANSPARENCY_WORKLOAD_CHAIN_PREFIX",
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