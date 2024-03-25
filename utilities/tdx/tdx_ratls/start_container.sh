#
# Copyright (c) 2024 Intel Corporation
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
    pccs_ip_addr=$1
else
    pccs_ip_addr=127.0.0.1
fi

if  [ -n "$2" ] ; then
    endpoint=$2
else
    endpoint=0.0.0.0:18501
fi

if  [ -n "$3" ] ; then
    image_tag=$3
else
    image_tag=tdx-ratls:ubuntu22.04-dcap1.19-latest
fi

# Use the host proxy as the default configuration, or specify a proxy_server
# no_proxy="localhost,127.0.0.1"
# proxy_server="" # your http proxy server

if [ "$proxy_server" != "" ]; then
    http_proxy=${proxy_server}
    https_proxy=${proxy_server}
fi

run_flags="
    -it --rm \
    --privileged=true \
    --net=host \
    --add-host=pccs.service.com:${pccs_ip_addr} \
    -v /dev:/dev \
    -v /home:/host/home \
    -e ENDPOINT=${endpoint} \
    -e no_proxy=${no_proxy} \
    -e http_proxy=${http_proxy} \
    -e https_proxy=${https_proxy} \
"
if [ -f "/var/run/aesmd/aesm.socket" ]; then
    echo "Start client ..."
    docker run ${run_flags} \
        -e ROLE="client" \
        --name="ratls-client" \
        -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
        ${image_tag} \
        bash
else
    echo "Start server ..."
    docker run ${run_flags} \
        -e ROLE="server" \
        --name="ratls-server" \
        ${image_tag} \
        bash
fi
