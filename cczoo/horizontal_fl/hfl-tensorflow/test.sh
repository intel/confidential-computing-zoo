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

#!/bin/bash
set -ex

function get_env() {
    gramine-sgx-get-token -s python.sig -o /dev/null | grep $1 | awk -F ":" '{print $2}' | xargs
}

function make_custom_env() {
    export CUDA_VISIBLE_DEVICES=""
    export DNNL_VERBOSE=1
    export GRPC_VERBOSITY=ERROR
    export TF_CPP_MIN_LOG_LEVEL=1
    # export TF_GRPC_SGX_RA_TLS_ENABLE=""
    export TF_GRPC_SGX_RA_TLS_ENABLE=on
    export TF_DISABLE_MKL=0
    export TF_ENABLE_MKL_NATIVE_FORMAT=1
    export parallel_num_threads=4
    export INTRA_OP_PARALLELISM_THREADS=$parallel_num_threads
    export INTER_OP_PARALLELISM_THREADS=$parallel_num_threads
    export KMP_SETTINGS=1
    export KMP_BLOCKTIME=0
    export MR_ENCLAVE=`get_env mr_enclave`
    export MR_SIGNER=`get_env mr_signer`
    export ISV_PROD_ID=`get_env isv_prod_id`
    export ISV_SVN=`get_env isv_svn`
    # network proxy
    unset http_proxy https_proxy
}

ROLE=$1
if [ "$ROLE" == "ps0" ]; then
    make_custom_env
    taskset -c 0-3 stdbuf -o0 python -u train.py --task_index=0 --job_name=ps --loglevel=debug 2>&1 | tee -a ps0-python.log &
if [ "$ROLE" == "ps1" ]; then
    make_custom_env
    taskset -c 4-7 stdbuf -o0 python -u train.py --task_index=1 --job_name=ps --loglevel=debug 2>&1 | tee -a ps1-python.log &
elif [ "$ROLE" == "worker0" ]; then
    make_custom_env
    taskset -c 8-11 stdbuf -o0 python -u train.py --task_index=0 --job_name=worker --loglevel=debug 2>&1 | tee -a worker0-python.log &
elif [ "$ROLE" == "worker1" ]; then
    make_custom_env
    taskset -c 12-15 stdbuf -o0 python -u train.py --task_index=1 --job_name=worker --loglevel=debug 2>&1 | tee -a worker1-python.log &
fi
