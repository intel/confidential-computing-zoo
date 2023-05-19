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

#!/usr/bin/env bash

set -e

if  [ ! -n "$1" ] ; then
    image_tag=tf_serving:latest
else
    image_tag=$1
fi

if  [ ! -n "$2" ] ; then
    container_name="tf-serving"
else
    container_name=$2
fi

ssl_configure=$3

# You can remove build-arg http_proxy and https_proxy if your network doesn't need it
proxy_server=""

docker run -itd \
    --name ${container_name} \
    -v ${ssl_configure}:/tmp/ssl_configure \
    ${image_tag} \
    .

docker commit ${container_name} ${image_tag}

docker rm -f ${container_name}
