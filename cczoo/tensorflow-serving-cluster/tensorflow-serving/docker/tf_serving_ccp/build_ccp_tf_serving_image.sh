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
    app_name=tensorflow_model_server
else
    app_name=$2
fi

if  [ ! -n "$3" ] ; then
    tmpl_file=tensorflow_model_server.toml
else
    tmpl_file=$3
fi

cp ${tmpl_file} /opt/ccp/template/${app_name}.toml

ccp-cli pack \
    --app-entry="/usr/bin/tensorflow_model_server" \
    --app-cmd="--model_name=resnet50-v15-fp32 \
               --model_base_path=/models/resnet50-v15-fp32 \
               --port=8500 \
               --rest_api_port=8501 \
               --enable_model_warmup=true \
               --flush_filesystem_caches=false \
               --enable_batching=false \
               --ssl_config_file=/ssl.cfg \
               --rest_api_num_threads=64 \
               --tensorflow_session_parallelism=0 \
               --tensorflow_intra_op_parallelism=2 \
               --tensorflow_inter_op_parallelism=2 \
               --file_system_poll_wait_seconds=5" \
    --tmpl=${app_name} \
    --secret-id=$4 \
    --secret-key=$5 \
    --capp-id=$6 \
    --app-image=${image_tag} \
    --app-type=image \
    --force
