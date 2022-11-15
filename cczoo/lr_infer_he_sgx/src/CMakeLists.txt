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

# Proto file
get_filename_component(infer_proto "inference.proto" ABSOLUTE)
get_filename_component(infer_proto_path "${infer_proto}" PATH)

# Generated sources
set(infer_proto_srcs "${CMAKE_CURRENT_BINARY_DIR}/inference.pb.cc")
set(infer_proto_hdrs "${CMAKE_CURRENT_BINARY_DIR}/inference.pb.h")
set(infer_grpc_srcs "${CMAKE_CURRENT_BINARY_DIR}/inference.grpc.pb.cc")
set(infer_grpc_hdrs "${CMAKE_CURRENT_BINARY_DIR}/inference.grpc.pb.h")
add_custom_command(
      OUTPUT "${infer_proto_srcs}" "${infer_proto_hdrs}" "${infer_grpc_srcs}" "${infer_grpc_hdrs}"
      COMMAND ${PROTOBUF_PROTOC}
      ARGS --grpc_out "${CMAKE_CURRENT_BINARY_DIR}"
        --cpp_out "${CMAKE_CURRENT_BINARY_DIR}"
        -I "${infer_proto_path}"
        --plugin=protoc-gen-grpc="${GRPC_CPP_PLUGIN_EXECUTABLE}"
        "${infer_proto}"
      DEPENDS "${infer_proto}")

# infer_grpc_proto
add_library(infer_grpc_proto
  ${infer_grpc_srcs}
  ${infer_grpc_hdrs}
  ${infer_proto_srcs}
  ${infer_proto_hdrs})
target_link_libraries(infer_grpc_proto
  ${REFLECTION}
  ${GRPC_GRPCPP}
  ${PROTOBUF_LIBPROTOBUF})

set(CLIENT_SRC infer_client.cpp infer_base.cpp utils.cpp param.cpp)
set(SERVER_SRC infer_server.cpp infer_base.cpp)

add_executable(infer_client ${CLIENT_SRC})
target_include_directories(infer_client
  PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
target_link_libraries(infer_client
  infer_grpc_proto
  libgflags
  ${SEAL_LIB}
  ${REFLECTION}
  ${GRPC_GRPCPP}
  ${PROTOBUF_LIBPROTOBUF})

add_executable(infer_server ${SERVER_SRC})
target_include_directories(infer_server
  PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
target_link_libraries(infer_server
  infer_grpc_proto
  libgflags
  ${SEAL_LIB}
  ${REFLECTION}
  ${GRPC_GRPCPP}
  ${PROTOBUF_LIBPROTOBUF})
