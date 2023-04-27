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

if  [ -n "$1" ] ; then
    name=$1
else
    name=ps0
fi

if  [ -n "$2" ] ; then
    ip_addr=$2
else
    ip_addr=127.0.0.1
fi

if  [ ! -n "$3" ] ; then
    tag=ali_tdx_latest
else
    tag=$3
fi

docker run -it \
    --restart=always \
    --cap-add=SYS_PTRACE \
    --security-opt seccomp=unconfined \
    --name=${name} \
    --privileged=true \
    -v /var/run/aesmd/aesm:/var/run/aesmd/aesm \
    -v /home:/home/host-home \
    -v /dev:/dev \
    --net=host \
    --add-host=pa.com:127.0.0.1 \
    --add-host=pb.com:127.0.0.1 \
    --add-host=pccs.service.com:${ip_addr} \
    horizontal_fl:${tag} \
    bash
