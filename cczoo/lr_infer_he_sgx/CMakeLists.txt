# Copyright (c) 2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
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

cmake_minimum_required(VERSION 3.15)

project(lr_infer_he_sgx)

option(ENABLE_INTEL_HEXL ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(cmake/seal.cmake)
include(cmake/grpc.cmake)
include(cmake/gflags.cmake)

include_directories("${CMAKE_CURRENT_BINARY_DIR}")
include_directories("${SEAL_INC_DIR}")

add_subdirectory(src)
