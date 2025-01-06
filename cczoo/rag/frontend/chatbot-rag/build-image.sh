#!/bin/bash
set -e
dockerfile=frontend.dockerfile
dcap_version=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --dcap-version) dcap_version="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

if [ -z "$dcap_version" ]; then
    echo "Error: --dcap-version is required, please visit this link to check the DCAP version: https://download.01.org/intel-sgx/sgx-dcap/"
    exit 1
fi

# You can remove build-arg http_proxy and https_proxy if your network doesn't neeed it
# no_proxy="localhost,127.0.0.0/1"
# proxy_server="" # your http proxy server

DOCKER_BUILDKIT=0 docker build \
    -f ${dockerfile} . \
    -t intelcczoo/tdx-rag:frontend \
    --network=host \
    --build-arg http_proxy=${http_proxy} \
    --build-arg https_proxy=${https_proxy} \
    --build-arg no_proxy=${no_proxy} \
    --build-arg DCAP_VERSION=${dcap_version}

