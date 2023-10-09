#!/bin/bash
set -e
dockerfile=backend.dockerfile
commit_id=fd25106c883bba36a4f5276792f024d4622130b3

# no_proxy="localhost,127.0.0.0/1"
# proxy_server="" # your http proxy server

docker build \
    -f ${dockerfile} . \
    -t appliedmlwf/rag-llm:release \
    --network=host \
    --build-arg http_proxy=${http_proxy} \
    --build-arg https_proxy=${https_proxy} \
    --build-arg no_proxy=${no_proxy} \
    --build-arg COMMIT_ID=${commit_id}
