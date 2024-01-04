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

# Use the host proxy as the default configuration, or specify a proxy_server
# no_proxy="localhost,127.0.0.1"
# proxy_server="" # your http proxy server

if [ "${proxy_server}" != "" ]; then
    http_proxy=${proxy_server}
    https_proxy=${proxy_server}
fi

cd `dirname $0`

function Usage() {
    echo "Usage: build_docker_image.sh kms  OR  build_docker_image.sh asps"
    echo "kms - KMS Server"
    echo "asps - Attestation and Secret Provisioning Service"
}

if [ -z $1 ]; then
    Usage
    exit 1
fi

if [ $1 = "kms" ]; then
    DOCKER_BUILDKIT=0 docker build \
        --build-arg no_proxy=${no_proxy} \
        --build-arg http_proxy=${http_proxy} \
        --build-arg https_proxy=${https_proxy} \
        -f kms_server.dockerfile \
        -t kms_server:latest \
        .
elif [ $1 = "asps" ];then
    DOCKER_BUILDKIT=0 docker build \
        --build-arg no_proxy=${no_proxy} \
        --build-arg http_proxy=${http_proxy} \
        --build-arg https_proxy=${https_proxy} \
        -f asp_service.dockerfile \
        -t asp_service:latest \
        .
else
    echo "Unsupported build target."
    Usage
    exit 1
fi

cd -
