#!/bin/bash
set -e
dockerfile=frontend.dockerfile

# You can remove build-arg http_proxy and https_proxy if your network doesn't neeed it
# no_proxy="localhost,127.0.0.0/1"
# proxy_server="" # your http proxy server

DOCKER_BUILDKIT=0 docker build \
    -f ${dockerfile} . \
    -t intelcczoo/tdx-rag:frontend \
    --network=host \
    --build-arg http_proxy=${http_proxy} \
    --build-arg https_proxy=${https_proxy} \
    --build-arg no_proxy=${no_proxy}

