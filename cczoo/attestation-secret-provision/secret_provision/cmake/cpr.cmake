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

set(CPR_ROOT ${CMAKE_BINARY_DIR}/cpr)
set(CPR_GIT_TAG  1.8.1)
set(CPR_GIT_URL  https://github.com/libcpr/cpr.git)
set(CPR_CONFIGURE    cd ${CPR_ROOT}/src/CPR && cmake -D CMAKE_INSTALL_PREFIX=${CMAKE_INSTALL_PREFIX} .)
set(CPR_MAKE         cd ${CPR_ROOT}/src/CPR && make)
set(CPR_INSTALL      cd ${CPR_ROOT}/src/CPR && make install)

ExternalProject_Add(CPR
        PREFIX            ${CPR_ROOT}
        GIT_REPOSITORY    ${CPR_GIT_URL}
        GIT_TAG           ${CPR_GIT_TAG}
        CONFIGURE_COMMAND ${CPR_CONFIGURE}
        BUILD_COMMAND     ${CPR_MAKE}
        INSTALL_COMMAND   ${CPR_INSTALL}
)

set(CPR_LIB ${CMAKE_INSTALL_PREFIX}/lib/libcpr.so)
set(CURL_LIB ${CMAKE_INSTALL_PREFIX}/lib/libcurl-d.so)
