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
    echo "Usage: start_container.sh [client | server]"
}

if  [ -z "$1" ]; then
    Usage
    exit 1
fi

# You can remove no_proxy and proxy_server if your network doesn't need it
no_proxy="localhost,127.0.0.1"
proxy_server="" # your http proxy server

if [ $1 = "client" ]; then
    container=$(echo `docker ps -a | grep infer_client`)
    if [ -n "${container}" ]; then
        docker stop infer_client && docker rm infer_client
    fi
    docker run --name infer_client \
        --network=host \
        --cap-add=SYS_PTRACE \
        --device=/dev/sgx_enclave:/dev/sgx/enclave \
        --device=/dev/sgx_provision:/dev/sgx/provision \
        -e no_proxy=${no_proxy} \
        -e http_proxy=${proxy_server} \
        -e https_proxy=${proxy_server} \
        lr_infer_he_sgx:latest \
        /lr_infer_he_sgx/build/src/infer_client --data datasets/lrtest_mid_eval.csv
elif [ $1 = "server" ]; then
    container=$(echo `docker ps -a | grep infer_server`)
    echo $container
    if [ -n "${container}" ]; then
        docker stop infer_server && docker rm infer_server
    fi
    docker run --name infer_server -it \
        --network=host \
        --restart=unless-stopped \
        --cap-add=SYS_PTRACE \
        --security-opt seccomp=unconfined \
        --device=/dev/sgx_enclave:/dev/sgx/enclave \
        --device=/dev/sgx_provision:/dev/sgx/provision \
        -e no_proxy=${no_proxy} \
        -e http_proxy=${proxy_server} \
        -e https_proxy=${proxy_server} \
        lr_infer_he_sgx:latest \
        bash
else
    Usage
    exit 1
fi
