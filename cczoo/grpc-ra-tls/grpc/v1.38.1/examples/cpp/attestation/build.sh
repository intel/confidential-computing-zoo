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

export EXP_PATH=`dirname $0`

if [ -z ${BUILD_TYPE} ]; then
    export BUILD_TYPE=Debug
fi

if [ -z ${SGX_RA_TLS_BACKEND} ]; then
    export SGX_RA_TLS_BACKEND=GRAMINE # GRAMINE,OCCLUM,DUMMY
fi

${GRPC_PATH}/build_cpp.sh

# build c++ example
cd ${EXP_PATH}
mkdir -p build
cd build
cmake -D CMAKE_PREFIX_PATH=${INSTALL_PREFIX} -D CMAKE_BUILD_TYPE=${BUILD_TYPE} ..
make -j `nproc`
../generate_ssl.sh -s localhost -a my_ca
cp ${GRPC_PATH}/dynamic_config.json .
cp ../secret.json .

cd -
