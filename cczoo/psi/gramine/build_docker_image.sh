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

if  [ ! -n "$1" ] ; then
    base_image=gramine-sgx-dev:ubuntu-18.04-latest
else
    base_image=$1
fi

if  [ ! -n "$2" ] ; then
    image_tag=psi_test
else
    image_tag=$2
fi

# You can remove no_proxy and proxy_server if your network doesn't need it
no_proxy="localhost,127.0.0.1"
# proxy_server="" # your http proxy server

cd `dirname $0`

DOCKER_BUILDKIT=0 docker build \
    --build-arg no_proxy=${no_proxy} \
    --build-arg http_proxy=${proxy_server} \
    --build-arg https_proxy=${proxy_server} \
    --build-arg BASE_IMAGE=${base_image} \
    -f psi-gramine-sgx-dev.dockerfile \
    -t ${image_tag} \
    ..

cd -
