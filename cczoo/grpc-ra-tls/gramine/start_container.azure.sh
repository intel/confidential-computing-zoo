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

function usage() {
    echo -e 'usage:'
    echo -e '  $0 ${image_id}'
    echo -e '  {image_id}'
    echo -e '       default: grpc-ratls-dev-azure:latest'
}

usage

if  [ -n "$1" ] ; then
    image_id=$1
else
    image_id=grpc-ratls-dev-azure:latest
fi

docker run -it \
    --privileged=true \
    --cap-add=SYS_PTRACE \
    --security-opt seccomp=unconfined \
    --device=/dev/sgx_enclave:/dev/sgx/enclave \
    --device=/dev/sgx_provision:/dev/sgx/provision \
    -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
    -v /home:/home/host-home \
    -e no_proxy=${no_proxy} \
    -e http_proxy=${http_proxy} \
    -e https_proxy=${https_proxy} \
    ${image_id} \
    bash
