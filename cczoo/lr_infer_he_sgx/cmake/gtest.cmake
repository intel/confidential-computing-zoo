# Copyright (C) 2020 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

include(ExternalProject)

set(GTEST_GIT_REPO_URL https://github.com/google/googletest.git)
set(GTEST_GIT_LABEL release-1.10.0)
set(GTEST_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC")

ExternalProject_Add(
  ext_gtest
  PREFIX ext_gtest
  GIT_REPOSITORY ${GTEST_GIT_REPO_URL}
  GIT_TAG ${GTEST_GIT_LABEL}
  CMAKE_ARGS ${BENCHMARK_FORWARD_CMAKE_ARGS} -DCMAKE_BUILD_TYPE=Release
  INSTALL_COMMAND ""
  UPDATE_COMMAND ""
  EXCLUDE_FROM_ALL TRUE)

ExternalProject_Get_Property(ext_gtest SOURCE_DIR BINARY_DIR)

add_library(libgtest INTERFACE)
add_dependencies(libgtest ext_gtest)

target_include_directories(libgtest SYSTEM
                           INTERFACE ${SOURCE_DIR}/googletest/include)
target_link_libraries(libgtest
                      INTERFACE ${BINARY_DIR}/lib/libgtest.a)

set(gtest_inc_dir ${SOURCE_DIR}/googletest/include)
set(gtest_lib ${BINARY_DIR}/lib/libgtest.a)