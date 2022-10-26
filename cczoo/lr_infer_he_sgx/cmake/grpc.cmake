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

message(STATUS "Using gRPC via add_subdirectory (FetchContent).")
include(FetchContent)
FetchContent_Declare(
  grpc
  GIT_REPOSITORY https://github.com/grpc/grpc.git
  GIT_TAG        v1.38.1)
FetchContent_MakeAvailable(grpc)

# Since FetchContent uses add_subdirectory under the hood, we can use
# the grpc targets directly from this build.
set(PROTOBUF_LIBPROTOBUF libprotobuf)
set(REFLECTION grpc++_reflection)
set(PROTOBUF_PROTOC $<TARGET_FILE:protoc>)
set(GRPC_GRPCPP grpc++)
set(GRPC_CPP_PLUGIN_EXECUTABLE $<TARGET_FILE:grpc_cpp_plugin>)
