# Proto file
# get_filename_component(infer_proto "inference.proto" ABSOLUTE)
# get_filename_component(infer_proto_path "${infer_proto}" PATH)

# Generated sources
# set(infer_proto_srcs "${CMAKE_CURRENT_BINARY_DIR}/inference.pb.cc")
# set(infer_proto_hdrs "${CMAKE_CURRENT_BINARY_DIR}/inference.pb.h")
# set(infer_grpc_srcs "${CMAKE_CURRENT_BINARY_DIR}/inference.grpc.pb.cc")
# set(infer_grpc_hdrs "${CMAKE_CURRENT_BINARY_DIR}/inference.grpc.pb.h")
# add_custom_command(
#       OUTPUT "${infer_proto_srcs}" "${infer_proto_hdrs}" "${infer_grpc_srcs}" "${infer_grpc_hdrs}"
#       COMMAND ${_PROTOBUF_PROTOC}
#       ARGS --grpc_out "${CMAKE_CURRENT_BINARY_DIR}"
#         --cpp_out "${CMAKE_CURRENT_BINARY_DIR}"
#         -I "${infer_proto_path}"
#         --plugin=protoc-gen-grpc="${_GRPC_CPP_PLUGIN_EXECUTABLE}"
#         "${infer_proto}"
#       DEPENDS "${infer_proto}")

# infer_grpc_proto
# add_library(infer_grpc_proto
#   ${infer_grpc_srcs}
#   ${infer_grpc_hdrs}
#   ${infer_proto_srcs}
#   ${infer_proto_hdrs})
# target_link_libraries(infer_grpc_proto
#   ${_REFLECTION}
#   ${_GRPC_GRPCPP}
#   ${_PROTOBUF_PROTOC})

# foreach(target
#   infer_client infer_server)
#   add_executable(${target} "${target}.cpp")
#   target_link_libraries(${target}
#     # infer_grpc_proto
#     # ${_REFLECTION}
#     # ${_GRPC_GRPCPP}
#     # ${_PROTOBUF_PROTOC}
#     ${SEAL_LIB})
# endforeach()

add_executable(infer_client infer_client.cpp infer_server.cpp utils.cpp param.cpp)
target_link_libraries(infer_client ${SEAL_LIB})