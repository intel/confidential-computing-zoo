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

if [ -z ${SGX_RA_TLS_BACKEND} ]; then
    export SGX_RA_TLS_BACKEND=GRAMINE # GRAMINE,OCCLUM,TDX,DUMMY
fi

if [ -z ${SGX_RA_TLS_SDK} ]; then
    export SGX_RA_TLS_SDK=DEFAULT # DEFAULT,LIBRATS
fi

${GRPC_PATH}/build_python.sh

cur_dir=`dirname $0`

mkdir -p ${cur_dir}/build

cp -r ${cur_dir}/*.py ${cur_dir}/build
cp ${GRPC_PATH}/dynamic_config.json ${cur_dir}/build
python3 -m grpc_tools.protoc -I ${GRPC_PATH}/examples/protos --python_out=${cur_dir}/build --grpc_python_out=${cur_dir}/build ratls.proto
