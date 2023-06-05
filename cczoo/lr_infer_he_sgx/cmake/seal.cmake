# Copyright (C) 2020 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

include(ExternalProject)

option(SEAL_PREBUILT OFF) # Set to ON/OFF to use prebuilt installation
message(STATUS "SEAL_PREBUILT: ${SEAL_PREBUILT}")

if (SEAL_PREBUILT) # Skip download from gitlab
  if (ENABLE_INTEL_HEXL)
    find_package(HEXL 1.2.3 HINTS ${INTEL_HEXL_HINT_DIR} REQUIRED)
  endif()
  find_package(SEAL 3.7
    HINTS ${SEAL_HINT_DIR}
    REQUIRED)
  add_library(libseal ALIAS SEAL::seal)
  # TODO(fboemer): Support pre-built shared seal
else()
  set(SEAL_PREFIX ${CMAKE_CURRENT_BINARY_DIR}/ext_seal)
  set(SEAL_SRC_DIR ${SEAL_PREFIX}/src/ext_seal/)
  set(SEAL_REPO_URL https://github.com/microsoft/SEAL.git)
  set(SEAL_GIT_TAG v3.7.2)

  set(SEAL_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fvisibility=hidden -fvisibility-inlines-hidden")

  set(SEAL_SHARED_LIB OFF) # Set to ON/OFF to toggle shared build

  if (ENABLE_INTEL_HEXL)
    ExternalProject_Add(
      ext_seal
      GIT_REPOSITORY ${SEAL_REPO_URL}
      GIT_TAG ${SEAL_GIT_TAG}
      PREFIX ${SEAL_PREFIX}
      INSTALL_DIR ${SEAL_PREFIX}
      CMAKE_ARGS ${BENCHMARK_FORWARD_CMAKE_ARGS}
        -DCMAKE_CXX_FLAGS=${SEAL_CXX_FLAGS}
        -DCMAKE_INSTALL_PREFIX=${SEAL_PREFIX}
        -DSEAL_USE_CXX17=ON
        -DCMAKE_INSTALL_LIBDIR=${SEAL_PREFIX}/lib
        -DCMAKE_INSTALL_INCLUDEDIR=${SEAL_PREFIX}/include
        -DSEAL_USE_INTEL_HEXL=${ENABLE_INTEL_HEXL}
        -DBUILD_SHARED_LIBS=${SEAL_SHARED_LIB}
      # Skip updates
      UPDATE_COMMAND ""
      )
  else()
    ExternalProject_Add(
      ext_seal
      GIT_REPOSITORY ${SEAL_REPO_URL}
      GIT_TAG ${SEAL_GIT_TAG}
      PREFIX ${SEAL_PREFIX}
      INSTALL_DIR ${SEAL_PREFIX}
      CMAKE_ARGS ${BENCHMARK_FORWARD_CMAKE_ARGS}
        -DCMAKE_INSTALL_PREFIX=${SEAL_PREFIX}
        -DSEAL_USE_CXX17=ON
        -DCMAKE_INSTALL_LIBDIR=${SEAL_PREFIX}/lib
        -DCMAKE_INSTALL_INCLUDEDIR=${SEAL_PREFIX}/include
        -DSEAL_USE_INTEL_HEXL=${ENABLE_INTEL_HEXL}
        -DBUILD_SHARED_LIBS=${SEAL_SHARED_LIB}
      # Skip updates
      UPDATE_COMMAND ""
      )
  endif()

  ExternalProject_Get_Property(ext_seal SOURCE_DIR BINARY_DIR)

  add_library(libseal INTERFACE)
  add_dependencies(libseal ext_seal)
  target_include_directories(libseal INTERFACE ${SEAL_PREFIX}/include/SEAL-3.7)

  if (SEAL_SHARED_LIB)
      target_link_libraries(libseal INTERFACE ${SEAL_PREFIX}/lib/libseal.so.3.7)
      set(SEAL_LIB ${SEAL_PREFIX}/lib/libseal.so.3.7)
  else()
      target_link_libraries(libseal INTERFACE ${SEAL_PREFIX}/lib/libseal-3.7.a)
      set(SEAL_LIB ${SEAL_PREFIX}/lib/libseal-3.7.a)
  endif()

endif()

set(SEAL_INC_DIR ${SEAL_PREFIX}/include/SEAL-3.7)
