#!/bin/bash
set -e

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

echo -e "\nbuild backend image..."
cd backend
./build-image.sh --dcap-version ${dcap_version}

sleep 1s

echo -e "\nbuild frontend image..."
cd ../frontend/chatbot-rag
./build-image.sh --dcap-version ${dcap_version}
