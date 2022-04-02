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

export EXP_PATH=${GRPC_PATH}/examples
export EXP_PY_PATH=${EXP_PATH}/python/ratls

function get_env() {
    gramine-sgx-get-token -s python.sig -o /dev/null | grep $1 | awk -F ":" '{print $2}' | xargs
}

# build example
${EXP_PY_PATH}/build.sh

# copy examples
cp ${EXP_PY_PATH}/client.py .
cp ${EXP_PY_PATH}/server.py .
cp ${EXP_PY_PATH}/ratls_pb2.py .
cp ${EXP_PY_PATH}/ratls_pb2_grpc.py .

# build and generate config json with gramine
make clean && make | logfilter
jq ' .sgx_mrs[0].mr_enclave = ''"'`get_env mr_enclave`'" | .sgx_mrs[0].mr_signer = ''"'`get_env mr_signer`'" ' ${GRPC_PATH}/dynamic_config.json > ./dynamic_config.json

kill -9 `pgrep -f gramine`
