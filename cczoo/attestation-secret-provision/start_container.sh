#
# Copyright (c) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#!/bin/bash
set -e

function Usage() {
    echo "Usage: start_container.sh [kms | asps] [ip_addr]"
}

if  [ -z "$1" ]; then
    Usage
    exit 1
fi

if  [ -n "$2" ]; then
    ip_addr=$2
else
    ip_addr=127.0.0.1
fi

# You can remove no_proxy and proxy_server if your network doesn't need it
no_proxy="localhost,127.0.0.1"
# proxy_server="" # your http proxy server

if [ $1 = "kms" ]; then
    # KMS server
    container=$(echo `docker ps -a | grep kms_server`)
    if [ -n "${container}" ]; then
        docker stop kms_server && docker rm kms_server
    fi
    docker run --name kms_server -d \
        --network=host \
        --cap-add=SYS_PTRACE \
        -e no_proxy=${no_proxy} \
        -e http_proxy=${proxy_server} \
        -e https_proxy=${proxy_server} \
        kms_server:latest \
        /kms_server/init_vault_server.sh
elif [ $1 = "asps" ]; then
    # Attestation and secret provision service
    container=$(echo `docker ps -a | grep asp_service`)
    echo $container
    if [ -n "${container}" ]; then
        docker stop asp_service && docker rm asp_service
    fi
    docker run --name asp_service -it \
        --network=host \
        --restart=unless-stopped \
        --cap-add=SYS_PTRACE \
        --security-opt seccomp=unconfined \
        --device=/dev/sgx_enclave:/dev/sgx/enclave \
        --device=/dev/sgx_provision:/dev/sgx/provision \
        --add-host=attestation.service.com:${ip_addr} \
        -e no_proxy=${no_proxy} \
        -e http_proxy=${proxy_server} \
        -e https_proxy=${proxy_server} \
        -v /home:/home/host-home \
        asp_service:latest \
        bash
else
    Usage
    exit 1
fi
