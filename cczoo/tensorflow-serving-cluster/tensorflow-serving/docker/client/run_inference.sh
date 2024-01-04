#!/usr/bin/bash
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

display_usage() {
    echo "Usage: $0 [oneway_ssl | twoway_ssl]"
}

if [ $# -ne 1 ]; then
    display_usage
    exit 1
fi

ssl=$1

if [[ ${ssl} == "oneway_ssl" ]]; then
    python3 ./resnet_client_grpc.py -batch 1 -cnum 1 -loop 50 -url grpc.tf-serving.service.com:8500 -crt `pwd -P`/ssl_configure/server/cert.pem
elif [[ ${ssl} == "twoway_ssl" ]]; then
    python3 ./resnet_client_grpc.py -batch 1 -cnum 1 -loop 50 -url grpc.tf-serving.service.com:8500 -ca `pwd -P`/ssl_configure/ca_cert.pem -crt `pwd -P`/ssl_configure/client/cert.pem -key `pwd -P`/ssl_configure/client/key.pem
else
    display_usage
    exit 1
fi
