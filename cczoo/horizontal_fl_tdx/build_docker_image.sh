#!/bin/bash
#
# Copyright (c) 2023 Intel Corporation
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

set -e

function usage() {
    echo -e "Usage: $0 BUILDTYPE [TAG]"
    echo -e "  BUILDTYPE      build type;"
    echo -e "                   BUILDTYPE is 'azure','gcp', or 'default'"
    echo -e "  TAG            docker tag suffix;"
    echo -e "                   docker tag is BUILDTYPE_TAG;"
    echo -e "                   TAG default is 'latest'"
}


if [ "$#" -lt 1 ]; then
    usage
    exit 1
fi

build_type=$1
if  [ "$1" != "azure" ] && [ "$1" != "gcp" ] && [ "$1" != "default" ]; then
    usage
    exit 1
fi

if  [ ! -n "$2" ] ; then
    tag=latest
else
    tag=$2
fi

DOCKER_BUILDKIT=0 docker build \
    -f horizontal_fl_tdx.${build_type}.dockerfile . \
    -t horizontal_fl_tdx:${build_type}_${tag} \
    --network=host \
    --build-arg http_proxy=${proxy_server} \
    --build-arg https_proxy=${proxy_server} \
    --build-arg no_proxy=${no_proxy} \
