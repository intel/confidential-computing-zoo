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

function usage_help() {
    echo -e "usage_help:"
    echo -e '  ./build_docker_image.sh ${base_image} ${image_tag} ${build_type}'
    echo -e "  {base_image}"
    echo -e "       ubuntu:18.04 | ubuntu20.04 | openanolis/anolisos:8.4-x86_64"
    echo -e "  {image_tag}"
    echo -e "       customed image tag"
    echo -e "  {docker_file}"
    echo -e "       gramine-sgx-dev.ubuntu.dockerfile | gramine-sgx-dev.anolisos.dockerfile"
}

usage_help

if  [ -n "$1" ] ; then
    base_image=$1
else
    base_image=ubuntu:20.04
fi

if  [ -n "$2" ] ; then
    image_tag=$2
else
    image_tag=gramine-sgx-dev:v1.2-ubuntu20.04-latest
fi

if  [ -n "$3" ] ; then
    docker_file=$3
else
    docker_file=gramine-sgx-dev.ubuntu.dockerfile
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
    --build-arg base_image=${base_image} \
    --build-arg BASE_IMAGE=${base_image} \
    -f ${docker_file} \
    -t ${image_tag} \
    .

cd -
