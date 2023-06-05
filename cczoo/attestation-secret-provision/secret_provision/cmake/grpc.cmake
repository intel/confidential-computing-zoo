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
include(ExternalProject)

set(GRPC_ROOT ${CMAKE_BINARY_DIR}/GRPC)
set(GRPC_GIT_TAG  v1.38.1)
set(GRPC_GIT_URL      https://github.com/grpc/grpc)
set(GRPC_CONFIGURE    cd ${GRPC_ROOT}/src/GRPC && cmake -D CMAKE_INSTALL_PREFIX=${CMAKE_INSTALL_PREFIX}
-D BUILD_SHARED_AND_STATIC_LIBS=On .)
set(GRPC_MAKE         cd ${GRPC_ROOT}/src/GRPC && make)
set(GRPC_INSTALL      cd ${GRPC_ROOT}/src/GRPC && make install)

ExternalProject_Add(GRPC
        PREFIX            ${GRPC_ROOT}
        GIT_REPOSITORY    ${GRPC_GIT_URL}
        GIT_TAG           ${GRPC_GIT_TAG}
        CONFIGURE_COMMAND ${GRPC_CONFIGURE}
        BUILD_COMMAND     ${GRPC_MAKE}
        INSTALL_COMMAND   ${GRPC_INSTALL}
)
