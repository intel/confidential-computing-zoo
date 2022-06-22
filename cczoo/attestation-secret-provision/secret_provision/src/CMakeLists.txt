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
add_library(secret_provision
            policy_manager.hpp policy_manager.cpp
            kms_agent.hpp kms_agent.cpp)
target_link_libraries(secret_provision ${CJSON_LIB} ${CURL_LIB} ${CPR_LIB})
set(HEADER_FILES
    ${CMAKE_CURRENT_SOURCE_DIR}/policy_manager.hpp
    ${CMAKE_CURRENT_SOURCE_DIR}/kms_agent.hpp)

install(FILES ${HEADER_FILES} DESTINATION ${CMAKE_INSTALL_PREFIX}/include)
install(TARGETS secret_provision
        LIBRARY DESTINATION lib
        ARCHIVE DESTINATION lib
        RUNTIME DESTINATION bin)