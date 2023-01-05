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

if  [ -n "$1" ] ; then
    image=$1
else
    image=confidential-inference:graminev1.2-ubuntu20.04-latest
fi

# You can remove no_proxy and proxy_server if your network doesn't need it
no_proxy="localhost,127.0.0.1"
# proxy_server="" # your http proxy server

function create_container() {
    container_name=$1
    server_address=$2
    docker rm -f ${container_name} || true
    docker run -itd \
        --name=${container_name} \
        --net=host \
        --cap-add=SYS_PTRACE \
        --device=/dev/sgx_enclave:/dev/sgx/enclave \
        --device=/dev/sgx_provision:/dev/sgx/provision \
        --add-host=infer.service.com:${server_address} \
        -e http_proxy=${proxy_server} \
        -e https_proxy=${proxy_server} \
        -e no_proxy=${no_proxy} \
        -v /home:/home/host-home \
        ${image}
}

create_container inf-server 127.0.0.1
create_container inf-client 127.0.0.1
create_container model-distributor 127.0.0.1

docker ps | grep -E 'model-distributor|inf-server|inf-client'
