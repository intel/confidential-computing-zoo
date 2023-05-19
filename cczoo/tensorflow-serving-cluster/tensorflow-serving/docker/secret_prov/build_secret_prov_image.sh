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

#!/usr/bin/env bash

set -e

if  [ ! -n "$2" ] ; then
    tag=latest
else
    tag=$2
fi

# You can remove build-arg http_proxy and https_proxy if your network doesn't need it
# proxy_server=""

if [ "$1" == "anolisos" ] ; then
DOCKER_BUILDKIT=0 docker build \
    -f secret_prov.anolisos.dockerfile \
    -t secret_prov_server:anolisos-${tag} \
    --build-arg http_proxy=${proxy_server} \
    --build-arg https_proxy=${proxy_server} \
    .
elif [ "$1" == "azure" ] ; then
DOCKER_BUILDKIT=0 docker build \
    -f secret_prov.azure.dockerfile \
    -t secret_prov_server:azure-${tag} \
    --build-arg http_proxy=${proxy_server} \
    --build-arg https_proxy=${proxy_server} \
    .
else
DOCKER_BUILDKIT=0 docker build \
    -f secret_prov.dockerfile \
    -t secret_prov_server:${tag} \
    --build-arg http_proxy=${proxy_server} \
    --build-arg https_proxy=${proxy_server} \
    .
fi
