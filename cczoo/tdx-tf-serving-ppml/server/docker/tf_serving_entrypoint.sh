#!/usr/bin/env bash

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
#

set -ex

unset http_proxy && unset https_proxy

ssl_config_file="/vfs/ssl_configure/ssl.cfg"
if [ ! -f "/vfs/ssl_configure/ssl.cfg" ]; then
    ssl_config_file=""
fi

env

tensorflow_model_server \
    --model_name=${model_name} \
    --model_base_path=/vfs/model/${model_name} \
    --port=8500 \
    --rest_api_port=8501 \
    --enable_model_warmup=true \
    --flush_filesystem_caches=false \
    --enable_batching=${enable_batching} \
    --ssl_config_file=${ssl_config_file} \
    --rest_api_num_threads=${rest_api_num_threads} \
    --tensorflow_session_parallelism=${session_parallelism} \
    --tensorflow_intra_op_parallelism=${intra_op_parallelism} \
    --tensorflow_inter_op_parallelism=${inter_op_parallelism} \
    --file_system_poll_wait_seconds=${file_system_poll_wait_seconds}
