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

export LIBRATS_ROOT=${GRPC_PATH}/build/librats

if [ ! -d "${LIBRATS_ROOT}" ]; then
    git clone https://github.com/inclavare-containers/librats.git ${LIBRATS_ROOT}
fi

cd ${LIBRATS_ROOT}

cmake -DRATS_BUILD_MODE="occlum" -H. -Bbuild
make -C build install

cd -
