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

set -ex

export ABSEIL_PATH=${GRPC_PATH}/third_party/abseil-cpp

if [ -z ${BUILD_TYPE} ]; then
    export BUILD_TYPE=Debug
fi

if [ -z ${SGX_RA_TLS_BACKEND} ]; then
    export SGX_RA_TLS_BACKEND=GRAMINE # GRAMINE,OCCLUM,TDX,DUMMY
fi

if [ "${SGX_RA_TLS_BACKEND}" == "TDX" ]; then
    cp ${GRPC_PATH}/dynamic_config.tdx.json ${GRPC_PATH}/dynamic_config.json
else
    cp ${GRPC_PATH}/dynamic_config.sgx.json ${GRPC_PATH}/dynamic_config.json
fi

cd ${GRPC_PATH}

echo 'RA_TLS_BACKEND = "'${SGX_RA_TLS_BACKEND}'"' > ${GRPC_PATH}/bazel/ratls.bzl
cat ${GRPC_PATH}/bazel/ratls.bzl

bazel build //:all --sandbox_debug -s -c dbg

cd -
