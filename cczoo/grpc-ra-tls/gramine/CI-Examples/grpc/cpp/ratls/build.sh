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

set -e

shopt -s expand_aliases
alias logfilter="grep \"mr_enclave\|mr_signer\|isv_prod_id\|isv_svn\""

GRPC_EXP_PATH=${GRPC_PATH}/examples
GRPC_EXP_CPP_PATH=${GRPC_EXP_PATH}/cpp
RUNTIME_TMP_PATH=/tmp/grpc_tmp_runtime
RUNTIME_PATH=`pwd -P`/runtime

function get_env() {
    gramine-sgx-get-token -s grpc.sig -o /dev/null | grep $1 | awk -F ":" '{print $2}' | xargs
}

function prepare_runtime() {
    rm -rf  ${RUNTIME_PATH} || true
    make clean && GRAPHENE_ENTRYPOINT=$1 make | logfilter && cp -r `pwd -P` ${RUNTIME_TMP_PATH}/$1
}

function generate_json() {
    cd ${RUNTIME_TMP_PATH}/$1
    jq ' .sgx_mrs[0].mr_enclave = ''"'`get_env mr_enclave`'" | .sgx_mrs[0].mr_signer = ''"'`get_env mr_signer`'" ' ${GRPC_PATH}/dynamic_config.json > ${RUNTIME_TMP_PATH}/$2/dynamic_config.json
    cd -
}

if [ -z ${BUILD_TYPE} ]; then
    export BUILD_TYPE=Debug
fi

if [ -z ${SGX_RA_TLS_BACKEND} ]; then
    export SGX_RA_TLS_BACKEND=GRAMINE # GRAMINE,OCCLUM,DUMMY
fi

# build examples
${GRPC_EXP_CPP_PATH}/ratls/build.sh

# copy examples
cp ${GRPC_EXP_CPP_PATH}/ratls/build/server .
cp ${GRPC_EXP_CPP_PATH}/ratls/build/client .

# create runtime tmp dir
rm -rf  ${RUNTIME_TMP_PATH} || true
mkdir -p ${RUNTIME_TMP_PATH}

# prepare runtime with gramine
prepare_runtime server
prepare_runtime client

# generate config json for sgx
generate_json server client
generate_json client server

rm -rf ${RUNTIME_PATH} || true
mv ${RUNTIME_TMP_PATH} ${RUNTIME_PATH}

kill -9 `pgrep -f gramine`
