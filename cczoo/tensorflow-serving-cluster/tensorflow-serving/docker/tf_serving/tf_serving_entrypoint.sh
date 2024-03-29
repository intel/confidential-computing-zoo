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

unset http_proxy && unset https_proxy

cd ${WORK_BASE_PATH}
# make SGX=${SGX} RA_TYPE=${RA_TYPE} -j `nproc`

if [ ${start_aesm_service} ]; then
    AESM="aesm_service"
    if pgrep -x "$AESM" > /dev/null
    then
        echo "$AESM is running"
    else
        echo "Attempting to start $AESM"
        mkdir -p /var/run/aesmd
        LD_LIBRARY_PATH="/opt/intel/sgx-aesm-service/aesm:$LD_LIBRARY_PATH" /opt/intel/sgx-aesm-service/aesm/aesm_service

        if pgrep -x "$AESM" > /dev/null
        then
            echo "$AESM is running"
        else
            echo "$AESM failed to start"
        fi
    fi
fi

# Bind Core 0-3
taskset -c 0-3 gramine-sgx tensorflow_model_server \
    --model_name=${model_name} \
    --model_base_path=/models/${model_name} \
    --port=8500 \
    --rest_api_port=8501 \
    --enable_model_warmup=true \
    --flush_filesystem_caches=false \
    --enable_batching=${enable_batching} \
    --ssl_config_file=${ssl_config_file} \
    --rest_api_num_threads=${rest_api_num_threads} \
    --tensorflow_session_parallelism=0 \
    --tensorflow_intra_op_parallelism=2 \
    --tensorflow_inter_op_parallelism=2 \
    --file_system_poll_wait_seconds=${file_system_poll_wait_seconds}

