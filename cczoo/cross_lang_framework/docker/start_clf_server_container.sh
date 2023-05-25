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
    ip_addr=$1
else
    ip_addr=127.0.0.1
fi

if  [ -n "$2" ] ; then
    image_tag=$2
else
    image_tag=clf-server:gramine1.3-ubuntu20.04
fi

# You can remove no_proxy and proxy_server if your network doesn't need it
no_proxy="localhost,127.0.0.1"
proxy_server="" # your http proxy server

docker run -it \
    --restart=unless-stopped \
    --cap-add=SYS_PTRACE \
    --security-opt seccomp=unconfined \
    --device=/dev/sgx_enclave:/dev/sgx/enclave \
    --device=/dev/sgx_provision:/dev/sgx/provision \
    --add-host=pccs.service.com:${ip_addr} \
    --net=host \
    -e no_proxy=${no_proxy} \
    -e http_proxy=${proxy_server} \
    -e https_proxy=${proxy_server} \
    -v /home:/home/host-home \
    -v `pwd -P`/../tools:/clf/cczoo/cross_lang_framework/clf_server/certs \
    -v `pwd -P`/../clf_server/clf_server.conf:/clf/cczoo/cross_lang_framework/clf_server/clf_server.conf \
    ${image_tag} \
    bash

