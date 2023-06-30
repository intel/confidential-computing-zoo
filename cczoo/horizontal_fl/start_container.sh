#!/bin/bash
#
# Copyright (c) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

function usage() {
    echo -e "Usage: $0 NAME IMAGE_ID [PCCS_IP]"
    echo -e "  NAME       Container name;"
    echo -e "                For example: ps0"
    echo -e "  IMAGE_ID   Container image ID;"
    echo -e "  PCCS_IP    Optional PCCS IP address;"
}


if [ "$#" -lt 2 ]; then
    usage
    exit 1
fi

name=${1}
image_id=${2}

if  [ -n "$3" ] ; then
    ip_addr=$3
else
    ip_addr=127.0.0.1
fi

docker run -itd \
    --restart=always \
    --cap-add=SYS_PTRACE \
    --security-opt seccomp=unconfined \
    --device=/dev/sgx_enclave:/dev/sgx/enclave \
    --device=/dev/sgx_provision:/dev/sgx/provision \
    --name=${name} \
    -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
    -v /home:/home/host-home \
    --net=host \
    --add-host=pccs.service.com:${ip_addr} \
    ${image_id} \
    bash
