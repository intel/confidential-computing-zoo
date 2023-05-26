#
# Copyright (c) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#!/bin/bash
set -e

if  [ -n "$1" ] ; then
    ip_addr=$1
else
    ip_addr=127.0.0.1
fi

# Please fill in the domain name where clf_server is deployed
if  [ -n "$2" ] ; then
    clf_server_domain_name=$2
else
    clf_server_domain_name=`hostname`
fi

if  [ -n "$3" ] ; then
    image_tag=$3
else
    image_tag=clf-client-app:gramine1.3-ubuntu20.04
fi


# You can remove no_proxy and proxy_server if your network doesn't need it
no_proxy="localhost,127.0.0.1"
proxy_server="" # your http proxy server

# You need to get ca_cert.crt by running the file ../tools/gen_cert.sh before running this script
docker run -it \
    --restart=unless-stopped \
    --cap-add=SYS_PTRACE \
    --security-opt seccomp=unconfined \
    --device=/dev/sgx_enclave:/dev/sgx/enclave \
    --device=/dev/sgx_provision:/dev/sgx/provision \
    --add-host=pccs.service.com:${ip_addr} \
    --add-host=${clf_server_domain_name}:${ip_addr} \
    -e no_proxy=${no_proxy} \
    -e http_proxy=${proxy_server} \
    -e https_proxy=${proxy_server} \
    -v /home:/home/host-home \
    -v `pwd -P`/../tools/ca_cert.crt:/clf/cczoo/cross_lang_framework/clf_client/app/certs/ca_cert.crt \
    -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
    ${image_tag} \
    bash

