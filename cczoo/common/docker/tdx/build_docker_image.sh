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

#!/bin/bash
set -e

if  [ -n "$1" ] ; then
    image_tag=$1
else
    image_tag=tdx-dev:dcap1.15-centos8-latest
fi

if  [ -n "$2" ] ; then
    docker_file=$2
else
    docker_file=tdx-dev.centos.dockerfile
fi

# Use the host proxy as the default configuration, or specify a proxy_server
# no_proxy="localhost,127.0.0.1"
# proxy_server="" # your http proxy server

if [ "$proxy_server" != "" ]; then
    http_proxy=${proxy_server}
    https_proxy=${proxy_server}
fi

cd `dirname $0`

DOCKER_BUILDKIT=0 docker build \
    --build-arg no_proxy=${no_proxy} \
    --build-arg http_proxy=${http_proxy} \
    --build-arg https_proxy=${https_proxy} \
    -f ${docker_file} \
    -t ${image_tag} \
    .

cd -
