#!/bin/bash
set -e
dockerfile=backend.dockerfile
commit_id=fd25106c883bba36a4f5276792f024d4622130b3
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

# no_proxy="localhost,127.0.0.0/1"
# proxy_server="" # your http proxy server

docker build \
    -f ${dockerfile} . \
    -t intelcczoo/tdx-rag:backend \
    --network=host \
    --build-arg http_proxy=${http_proxy} \
    --build-arg https_proxy=${https_proxy} \
    --build-arg no_proxy=${no_proxy} \
    --build-arg DCAP_VERSION=${dcap_version} \
    --build-arg COMMIT_ID=${commit_id}
