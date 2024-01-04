#!/usr/bin/env bash

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

set -e

function usage_help() {
    echo -e "options:"
    echo -e "  -h Display help"
    echo -e "  -i {image_id}"
    echo -e "  -p {host_ports}"
    echo -e "  -a {attestation_hosts}"
    echo -e "       Format: '{attestation_domain_name}:{ip}'"
}

# Default args
host_ports=""
cur_dir=`pwd -P`
attestation_hosts="localhost:127.0.0.1"
http_proxy=""
https_proxy=""
no_proxy=""
image_id=sec_tf_serving:latest

# Override args
while getopts "h?r:i:p:m:s:a:e:" OPT; do
    case $OPT in
        h|\?)
            usage_help
            exit 1
            ;;
        i)
            echo -e "Option $OPTIND, image_id = $OPTARG"
            image_id=$OPTARG
            ;;
        p)
            echo -e "Option $OPTIND, host_ports = $OPTARG"
            host_ports=$OPTARG
            ;;
        a)
            echo -e "Option $OPTIND, attestation_hosts = $OPTARG"
            attestation_hosts=$OPTARG
            ;;
        :)
            echo -e "Option $OPTARG needs argument"
            usage_help
            exit 1
            ;;
        ?)
            echo -e "Unknown option $OPTARG"
            usage_help
            exit 1
            ;;
    esac
done

docker run \
    -it \
    --device /dev/sgx_enclave:/dev/sgx/enclave \
    --device /dev/sgx_provision:/dev/sgx/provision \
    --add-host=${attestation_hosts} \
    -p ${host_ports}:8500-8501 \
    -e http_proxy=${http_proxy} \
    -e https_proxy=${https_proxy} \
    -e no_proxy=${no_proxy} \
    ${image_id}