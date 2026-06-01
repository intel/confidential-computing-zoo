from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import runtime
from .request_auth import enforce_authenticated_request
from .routers import build, delegation, launch, luks, publish, results, sigstore


app = FastAPI(
    title="TC API - Trusted Container Build and Publish Service",
    description="RESTful API for building, signing, encrypting and publishing Docker images",
    version="1.0.0",
    lifespan=runtime.lifespan,
)

runtime.ensure_runtime_dirs()


@app.middleware("http")
async def limit_build_package_request_size(request: Request, call_next):
    if request.url.path == "/api/build-package" and request.method.upper() == "POST":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > runtime.BUILD_PACKAGE_MAX_REQUEST_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": (
                                "Build package payload too large. "
                                f"Limit is {runtime.BUILD_PACKAGE_MAX_REQUEST_BYTES} bytes."
                            )
                        },
                    )
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})
    return await call_next(request)


@app.middleware("http")
async def authenticate_write_requests(request: Request, call_next):
    denial = await enforce_authenticated_request(request)
    if denial is not None:
        return denial
    return await call_next(request)

app.include_router(sigstore.router)
app.include_router(build.router)
app.include_router(publish.router)
app.include_router(launch.router)
app.include_router(results.router)
app.include_router(luks.router)
app.include_router(delegation.router)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=runtime.HOST, port=runtime.PORT, log_level=runtime.LOG_LEVEL.lower())


__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
