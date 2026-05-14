import os

from fastapi import FastAPI

from . import runtime
from .routers import build, delegation, launch, luks, publish, results, sigstore


app = FastAPI(
    title="TC API - Trusted Container Build and Publish Service",
    description="RESTful API for building, signing, encrypting and publishing Docker images",
    version="1.0.0",
    lifespan=runtime.lifespan,
)

runtime.ensure_runtime_dirs()

app.include_router(sigstore.router)
app.include_router(build.router)
app.include_router(publish.router)
app.include_router(launch.router)
app.include_router(results.router)
app.include_router(luks.router)
app.include_router(delegation.router)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=runtime.HOST, port=runtime.PORT, log_level="debug")


__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
