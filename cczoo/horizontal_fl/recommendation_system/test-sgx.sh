#!/bin/bash
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

set -ex

shopt -s expand_aliases
alias make_logfilter="grep \"mr_enclave\|mr_signer\|isv_prod_id\|isv_svn\""
alias runtime_logfilter="grep -v \"FUTEX\|measured\|memory entry\|cleaning up\|async event\|shim_exit\""

function get_env() {
    gramine-sgx-get-token -s python.sig -o /dev/null | grep $1 | awk -F ":" '{print $2}' | xargs
}

function make_custom_env() {
    export DEBUG=0
    export CUDA_VISIBLE_DEVICES=""
    export DNNL_VERBOSE=1
    export GRPC_POLL_STRATEGY=epoll1
    export GRPC_VERBOSITY=ERROR
    export TF_CPP_MIN_LOG_LEVEL=1
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
    unset http_proxy https_proxy
}

ROLE=$1

if [ "$ROLE" == "make" ]; then
    make clean && make | make_logfilter
elif [ "$ROLE" == "ps0" ]; then
    make_custom_env
    taskset -c 0-8 stdbuf -o0 gramine-sgx python -u ps0.py 2>&1 | runtime_logfilter | tee -a ps0.log &
    if [ "$DEBUG" != "0" ]; then
        wait && kill -9 `pgrep -f gramine`
    fi
elif [ "$ROLE" == "worker0" ]; then
    make_custom_env
    taskset -c 9-17 stdbuf -o0 gramine-sgx python -u worker0.py 2>&1 | runtime_logfilter | tee -a worker0.log &
    if [ "$DEBUG" != "0" ]; then
        wait && kill -9 `pgrep -f gramine`
    fi
elif [ "$ROLE" == "worker1" ]; then
    make_custom_env
    taskset -c 18-26 stdbuf -o0 gramine-sgx python -u worker1.py 2>&1 | runtime_logfilter | tee -a worker1.log &
    if [ "$DEBUG" != "0" ]; then
        wait && kill -9 `pgrep -f gramine`
    fi
elif [ "$ROLE" == "worker2" ]; then
    make_custom_env
    taskset -c 27-35 stdbuf -o0 gramine-sgx python -u worker2.py 2>&1 | runtime_logfilter | tee -a worker2.log &
    if [ "$DEBUG" != "0" ]; then
        wait && kill -9 `pgrep -f gramine`
    fi
elif [ "$ROLE" == "worker3" ]; then
    make_custom_env
    taskset -c 36-44 stdbuf -o0 gramine-sgx python -u worker3.py 2>&1 | runtime_logfilter | tee -a worker3.log &
    if [ "$DEBUG" != "0" ]; then
        wait && kill -9 `pgrep -f gramine`
    fi
fi
