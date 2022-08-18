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

if [ -z ${DEBUG} ]; then
    export DEBUG=1
fi

if [ -z ${SGX_RA_TLS_BACKEND} ]; then
    export SGX_RA_TLS_BACKEND=GRAMINE # GRAMINE,OCCLUM,DUMMY
fi

if [ -z ${SGX_RA_TLS_SDK} ]; then
    export SGX_RA_TLS_SDK=DEFAULT # DEFAULT,LIBRATS
fi

# build grpc c / cpp library
${GRPC_PATH}/build_cpp.sh

# build grpc python wheel
cd ${GRPC_PATH}
rm -rf python_build None src/python/grpcio/__pycache__ src/python/grpcio/grpc/_cython/cygrpc.cpp
SGX_RA_TLS_BACKEND=${SGX_RA_TLS_BACKEND} python3 -c "import os; print(os.getenv('SGX_RA_TLS_BACKEND'))"
SGX_RA_TLS_BACKEND=${SGX_RA_TLS_BACKEND} python3 setup.py bdist_wheel
cd -

ldd ${GRPC_PATH}/python_build/lib.linux-x86_64-*/grpc/_cython/cygrpc.cpython-*-x86_64-linux-gnu.so

pip3 uninstall -y grpcio
pip3 install ${GRPC_PATH}/dist/*.whl
pip3 install grpcio-tools==1.38.1

python3 -u -c "import grpc"
