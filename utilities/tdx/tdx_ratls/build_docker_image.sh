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

if  [ ! -n "$1" ] ; then
    image_tag=tdx-ratls:ubuntu22.04-dcap1.19-latest
else
    image_tag=$2
fi

if  [ ! -n "$2" ] ; then
    base_image=ubuntu:22.04
else
    base_image=$1
fi

if  [ ! -n "$3" ] ; then
    docker_file=Dockerfile
else
    docker_file=$3
fi

# Use the host proxy as the default configuration, or specify a proxy_server
# no_proxy="localhost,127.0.0.1"
# proxy_server="" # your http proxy server

if [ "$proxy_server" != "" ]; then
    http_proxy=${proxy_server}
    https_proxy=${proxy_server}
fi

cd `dirname $0`

docker build \
    --build-arg no_proxy=${no_proxy} \
    --build-arg http_proxy=${http_proxy} \
    --build-arg https_proxy=${https_proxy} \
    --build-arg BASE_IMAGE=${base_image} \
    -f ${docker_file} \
    -t ${image_tag} \
    .

cd -
