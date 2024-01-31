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

function usage() {
    echo -e "usage:"
    echo -e '  ./build_docker_image.azure.sh ${tag}'
    echo -e "  {tag}"
    echo -e "       custom image tag, default: latest"
}

usage

if  [ -n "$1" ] ; then
    tag=$1
else
    tag=latest
fi

docker build \
    --build-arg no_proxy=${no_proxy} \
    --build-arg http_proxy=${http_proxy} \
    --build-arg https_proxy=${https_proxy} \
    -f gramine-sgx-dev.azure.dockerfile \
    -t gramine-sgx-dev-azure:${tag} \
    .
