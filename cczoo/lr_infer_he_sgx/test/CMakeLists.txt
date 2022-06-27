set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)

set(SRC 
    unit_test.cpp
    ${CMAKE_SOURCE_DIR}/src/infer_client.cpp
    ${CMAKE_SOURCE_DIR}/src/infer_server.cpp
    ${CMAKE_SOURCE_DIR}/src/utils.cpp
    ${CMAKE_SOURCE_DIR}/src/param.cpp)

add_executable(unit_test ${SRC})

# target_include_directories(unit_test ${CMAKE_SOURCE_DIR}/src)
# target_include_directories(unit_test ${SEAL_INC_DIR})
target_include_directories(unit_test INTERFACE ${gtest_inc_dir})
target_link_libraries(unit_test libgtest ${SEAL_LIB})
target_link_libraries(unit-test PRIVATE Threads::Threads)
