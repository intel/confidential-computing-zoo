#
# Copyright (c) 2021 Intel Corporation
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

if  [ ! -n "$1" ] ; then
    workload=image_classification
else
    workload=$1
fi

if  [ ! -n "$2" ] ; then
    tag=latest
else
    tag=$2
fi

if  [ -z "$AZURE" ] ; then
    azure=
else
    azure=1
fi

# You can remove build-arg http_proxy and https_proxy if your network doesn't need it
# no_proxy="localhost,127.0.0.0/1"
# proxy_server="" # your http proxy server

DOCKER_BUILDKIT=0 docker build \
    -f horizontal_fl.dockerfile . \
    -t horizontal_fl:${tag} \
    --network=host \
    --build-arg http_proxy=${proxy_server} \
    --build-arg https_proxy=${proxy_server} \
    --build-arg no_proxy=${no_proxy} \
    --build-arg AZURE=${azure} \
    --build-arg WORKLOAD=${workload} \
