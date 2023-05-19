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

#!/usr/bin/env bash

set -e

function usage() {
    echo -e "Usage: $0 [OPTION]"
    echo -e "  -h             display this help text and exit"
    echo -e "  -b BUILDTYPE   build type;"
    echo -e "                   BUILDTYPE is 'anolisos', or 'default';"
    echo -e "                   BUILDTYPE default is 'default'"
    echo -e "  -t TAG         docker tag suffix;"
    echo -e "                   docker tag is BUILDTYPE_client_TAG;"
    echo -e "                   TAG default is 'latest'"
    echo -e "  -p PROXY       proxy info;"
    echo -e "                   PROXY format is http://proxyserver:port;"
    echo -e "                   PROXY default is no proxy"
}

build_type="default"
tag="latest"
proxy_server=""
repo_name="tensorflow_serving"

while getopts "h?b:t:p:" OPT; do
    case $OPT in
        h|\?)
            usage
            exit 1
            ;;
        b)
            echo -e "BUILDTYPE = $OPTARG"
            build_type=$OPTARG
            ;;
        t)
            echo -e "TAG = $OPTARG"
            tag=$OPTARG
            ;;
        p)
            echo -e "PROXY = $OPTARG"
            proxy_server=$OPTARG
            ;;
        ?)
            echo -e "Unknown option $OPTARG"
            usage
            exit 1
            ;;
    esac
done

if [ "$build_type" == "anolisos" ] ; then
DOCKER_BUILDKIT=0 docker build \
    -f anolisos_client.dockerfile \
    -t ${repo_name}:anolis_client_${tag} \
    --build-arg http_proxy=${proxy_server} \
    --build-arg https_proxy=${proxy_server} \
    .
elif [ "$build_type" == "default" ] ; then
DOCKER_BUILDKIT=0 docker build \
    -f client.dockerfile \
    -t ${repo_name}:default_client_${tag} \
    --build-arg http_proxy=${proxy_server} \
    --build-arg https_proxy=${proxy_server} \
    .
else
    echo -e "Invalid BUILDTYPE"
    usage
    exit 1
fi
