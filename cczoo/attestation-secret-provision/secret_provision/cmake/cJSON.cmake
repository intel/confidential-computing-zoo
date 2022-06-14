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

set(CJSON_ROOT ${CMAKE_BINARY_DIR}/cJSON)
set(CJSON_GIT_TAG  v1.7.15)
set(CJSON_GIT_URL      https://github.com/DaveGamble/cJSON.git)
set(CJSON_CONFIGURE    cd ${CJSON_ROOT}/src/CJSON && cmake -D CMAKE_INSTALL_PREFIX=${CMAKE_INSTALL_PREFIX}
-D BUILD_SHARED_AND_STATIC_LIBS=On .)
set(CJSON_MAKE         cd ${CJSON_ROOT}/src/CJSON && make)
set(CJSON_INSTALL      cd ${CJSON_ROOT}/src/CJSON && make install)

ExternalProject_Add(CJSON
        PREFIX            ${CJSON_ROOT}
        GIT_REPOSITORY    ${CJSON_GIT_URL}
        GIT_TAG           ${CJSON_GIT_TAG}
        CONFIGURE_COMMAND ${CJSON_CONFIGURE}
        BUILD_COMMAND     ${CJSON_MAKE}
        INSTALL_COMMAND   ${CJSON_INSTALL}
)

set(CJSON_LIB ${CMAKE_INSTALL_PREFIX}/lib/libcjson.so)
