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
set -x

shopt -s expand_aliases
alias logfilter="grep \"mr_enclave\|mr_signer\|isv_prod_id\|isv_svn\""

GRPC_EXP_PATH=${GRPC_PATH}/examples
GRPC_EXP_CPP_PATH=${GRPC_EXP_PATH}/cpp
RUNTIME_TMP_PATH=/tmp/grpc_tmp_runtime
RUNTIME_PATH=`pwd -P`/runtime

function get_env() {
    gramine-sgx-get-token -s grpc.sig -o /dev/null | grep $1 | awk -F ":" '{print $2}' | xargs
}

function perpare_json() {
    cp ${GRPC_PATH}/dynamic_config.json dynamic_config_$1.json
    cp ${GRPC_PATH}/dynamic_config.json dynamic_config_$2.json
    cp ${GRPC_PATH}/dynamic_config.json dynamic_config_$3.json
    cp ${GRPC_PATH}/dynamic_config.json dynamic_config_$4.json
}

function prepare_runtime() {
    make clean && GRAPHENE_ENTRYPOINT=$1 make | logfilter
    jq --argjson groupInfo '{"mr_enclave":''"'`get_env mr_enclave`'", "mr_signer": ''"'`get_env mr_signer`'", "isv_prod_id": "0", "isv_svn": "0"}' \
    '.sgx_mrs += [$groupInfo]' dynamic_config_$2.json > dynamic_config_$2_tmp.json
    mv dynamic_config_$2_tmp.json dynamic_config_$2.json
    cp -r `pwd -P` ${RUNTIME_TMP_PATH}/$1

}

function config_json() {
    rm -f ${RUNTIME_TMP_PATH}/$1/dynamic_config_*.json
    mv dynamic_config_$1.json ${RUNTIME_TMP_PATH}/$1/dynamic_config.json
}

if [ -z ${BUILD_TYPE} ]; then
    export BUILD_TYPE=Debug
fi

if [ -z ${SGX_RA_TLS_BACKEND} ]; then
    export SGX_RA_TLS_BACKEND=GRAMINE # GRAMINE,OCCLUM,TDX,DUMMY
fi

# build examples
${GRPC_EXP_CPP_PATH}/psi/build.sh

# copy examples
cp ${GRPC_EXP_CPP_PATH}/psi/build/server .
cp ${GRPC_EXP_CPP_PATH}/psi/build/data_provider1 .
cp ${GRPC_EXP_CPP_PATH}/psi/build/data_provider2 .
cp ${GRPC_EXP_CPP_PATH}/psi/build/data_provider3 .

# create runtime tmp dir
rm -rf  ${RUNTIME_TMP_PATH} || true
mkdir -p ${RUNTIME_TMP_PATH}

# prepare runtime with gramine & generate config json for sgx
rm -rf  ${RUNTIME_PATH} || true
perpare_json server data_provider1 data_provider2 data_provider3
prepare_runtime server data_provider1
prepare_runtime server data_provider2
prepare_runtime server data_provider3
prepare_runtime data_provider1 server
prepare_runtime data_provider2 server
prepare_runtime data_provider3 server
config_json server
config_json data_provider1
config_json data_provider2
config_json data_provider3

rm -rf ${RUNTIME_PATH} || true
mv ${RUNTIME_TMP_PATH} ${RUNTIME_PATH}

kill -9 `pgrep -f gramine`
