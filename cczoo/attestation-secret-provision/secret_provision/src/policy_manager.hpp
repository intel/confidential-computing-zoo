/*
 *
 * Copyright (c) 2022 Intel Corporation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 */
#ifndef _POLICY_MANAGER_HPP_
#define _POLICY_MANAGER_HPP_

#include <iostream>
#include <memory>
#include <string>
#include <map>
#include "cjson/cJSON.h"
#include "kms_agent.hpp"

namespace as {
class PolicyManager {
public:
PolicyManager(std::string& policy_file);
~PolicyManager();
void updatePolicy(std::string& policy_file);
std::string getKMSAddr();
KMSType getKMSType() {
  return kms_type_;
};
std::string getAppToken(std::string& mr_enclave);
std::string getSecretPath(std::string& mr_enclave,
                          std::string& secret_name);
std::map<std::string, std::string> getSecretPathList(
  std::string& mr_enclave);
std::shared_ptr<KMSAgent> createKMSAgent(std::string& mr_enclave);
private:
void loadJsonFile(std::string& file_name);
void closeJsonHandle();
bool cmpItem(cJSON* obj, const char* item);
void initKMSType();

cJSON* json_handle_;
KMSType kms_type_;
};
}
#endif  // _POLICY_MANAGER_HPP_