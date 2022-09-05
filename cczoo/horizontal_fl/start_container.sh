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
    tag=latest
else
    tag=$3
fi

if [ "$4" == "ubuntu" ] || [ -n "$4" ]; then
docker run -it \
    --restart=always \
    --cap-add=SYS_PTRACE \
    --security-opt seccomp=unconfined \
    --device=/dev/sgx_enclave:/dev/sgx/enclave \
    --device=/dev/sgx_provision:/dev/sgx/provision \
    --name=${name} \
    -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
    -v /home:/home/host-home \
	--net=host \
    --add-host=pccs.service.com:${ip_addr} \
    horizontal_fl:${tag} \
    bash
elif [ "$4" == "anolisos" ]; then
docker run -it \
    --restart=always \
    --cap-add=SYS_PTRACE \
    --security-opt seccomp=unconfined \
    --device=/dev/sgx_enclave:/dev/sgx/enclave \
    --device=/dev/sgx_provision:/dev/sgx/provision \
    --name=${name} \
    -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
    -v /home:/home/host-home \
    --net=host \
    --add-host=pccs.service.com:${ip_addr} \
    anolisos_horizontal_fl:${tag} \
    bash
fi   