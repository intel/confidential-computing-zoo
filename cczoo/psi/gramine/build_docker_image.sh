#!/bin/bash
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

set -e

if  [ "$1" == "anolisos" ] ; then
    base_image=$1
else
    base_image=ubuntu:20.04
fi

if  [ -z "$AZURE" ] ; then
    azure=
else
    azure=1
fi

# You can remove no_proxy and proxy_server if your network doesn't need it
no_proxy="localhost,127.0.0.1"
proxy_server="" # your http proxy server

cd `dirname $0`

if [ ${base_image} == "anolisos" ] ; then
DOCKER_BUILDKIT=0 docker build \
    --build-arg no_proxy=${no_proxy} \
    --build-arg http_proxy=${proxy_server} \
    --build-arg https_proxy=${proxy_server} \
    --build-arg BASE_IMAGE=gramine-sgx-dev:v1.2-anolisos\
    -f anolisos-psi-gramine-sgx-dev.dockerfile \
    -t anolisos_psi \
    ..
else
DOCKER_BUILDKIT=0 docker build \
    --build-arg no_proxy=${no_proxy} \
    --build-arg http_proxy=${proxy_server} \
    --build-arg https_proxy=${proxy_server} \
    --build-arg BASE_IMAGE=${base_image} \
    --build-arg AZURE=${azure} \
    -f psi-gramine-sgx-dev.dockerfile \
    -t psi \
    ..
fi
cd -
