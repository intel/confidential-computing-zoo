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
    echo -e "Usage: $0 WORKLOADTYPE BUILDTYPE [TAG]"
    echo -e "  WORKLOADTYPE   workload type;"
    echo -e "                   WORKLOADTYPE is 'image_classification' or 'recommendation_system'"
    echo -e "  BUILDTYPE      build type;"
    echo -e "                   BUILDTYPE is 'azure', 'anolisos', or 'default'"
    echo -e "  TAG            docker tag suffix;"
    echo -e "                   docker tag is BUILDTYPE_TAG;"
    echo -e "                   TAG default is 'latest'"
}


if [ "$#" -lt 2 ]; then
    usage
    exit 1
fi

workload_type=${1}
if  [ "$1" != "image_classification" ] && [ "$1" != "recommendation_system" ]; then
    usage
    exit 1
fi

build_type=${2}
if  [ "$2" != "azure" ] && [ "$2" != "anolisos" ] && [ "$2" != "default" ]; then
    usage
    exit 1
fi

if  [ ! -n "$3" ] ; then
    tag=latest
else
    tag=$3
fi

DOCKER_BUILDKIT=0 docker build \
    -f horizontal_fl.${build_type}.dockerfile . \
    -t horizontal_fl:${build_type}_${workload_type}_${tag} \
    --network=host \
    --build-arg http_proxy=${proxy_server} \
    --build-arg https_proxy=${proxy_server} \
    --build-arg no_proxy=${no_proxy} \
    --build-arg WORKLOAD=${workload_type} \
