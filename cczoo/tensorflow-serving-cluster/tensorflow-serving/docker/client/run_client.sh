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

unset -v ipaddr
unset -v image_id
unset -v ssl_dir

function usage() {
    echo -e "Usage: $0 -s <SSLDIR> -t <IPADDR> -i <IMAGEID>"
    echo -e "  -h             display this help text and exit"
    echo -e "  -s SSLDIR      SSLDIR is the absolute path to the ssl_configure directory"
    echo -e "  -t IPADDR      IPADDR is the TF serving service IP address"
    echo -e "  -i IMAGEID     IMAGEID is the client docker image ID"
}

while getopts "h?s:t:i:" OPT; do
    case $OPT in
        h|\?)
            usage
            exit 1
            ;;
        s)
            echo -e "SSLDIR = $OPTARG"
            ssl_dir=$OPTARG
            ;;
        t)
            echo -e "IPADDR = $OPTARG"
            ipaddr=$OPTARG
            ;;
        i)
            echo -e "IMAGEID = $OPTARG"
            image_id=$OPTARG
            ;;
        ?)
            echo -e "Unknown option $OPTARG"
            usage
            exit 1
            ;;
    esac
done

if [ -z "$ipaddr" ] || [ -z "$image_id" ] || [ -z "$ssl_dir" ]; then
    usage
    exit 1
fi


docker run -it -v ${ssl_dir}/ca_cert.pem:/client/ssl_configure/ca_cert.pem \
       -v ${ssl_dir}/client/cert.pem:/client/ssl_configure/client/cert.pem \
       -v ${ssl_dir}/client/key.pem:/client/ssl_configure/client/key.pem \
       -v ${ssl_dir}/server/cert.pem:/client/ssl_configure/server/cert.pem \
       --add-host="grpc.tf-serving.service.com:${ipaddr}" \
       ${image_id} bash
