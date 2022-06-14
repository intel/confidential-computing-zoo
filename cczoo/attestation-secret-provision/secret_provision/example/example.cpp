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
#include <iostream>
#include "policy_manager.hpp"
#include "kms_agent.hpp"

using namespace as;

int main(){
  std::string policy_file = "../../policy_file/policy_vault.json";
  auto policy_manager = PolicyManager(policy_file);
  std::string mr_enclave1 = "abc";
  std::string mr_enclave2 = "def";
  auto kms_agent1 = policy_manager.createKMSAgent(mr_enclave1);
  std::string secret_name = "master_key";
  std::string image_key = kms_agent1->getSecret(secret_name);
  std::cout << "image key: " << image_key << std::endl;
}
