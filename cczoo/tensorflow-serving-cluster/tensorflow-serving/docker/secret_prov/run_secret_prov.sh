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
    echo -e "  -a {pccs_service_com}"
}

pccs_service_com="localhost:127.0.0.1"

while getopts "h?i:a:" OPT; do
    case $OPT in
        h|\?)
            usage_help
            exit 1
            ;;
        i)
            echo -e "Option $OPTIND, image_id = $OPTARG"
            image_id=$OPTARG
            ;;
        a)
            echo -e "Option $OPTIND, pccs_service_com = $OPTARG"
            pccs_service_com=$OPTARG
            ;;      
        ?)
            echo -e "Unknown option $OPTARG"
            usage_help
            exit 1
            ;;
    esac
done

docker run -itd -p 4433:4433 \
       -v /var/run/aesmd/aesm.socket:/var/run/aesmd/aesm.socket \
       --add-host=${pccs_service_com} \
       ${image_id}
