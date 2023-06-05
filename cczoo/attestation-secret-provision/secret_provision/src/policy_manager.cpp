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
#include <cstring>
#include "cpr/cpr.h"
#include "policy_manager.hpp"

namespace as {
PolicyManager::PolicyManager(std::string& policy_file) {
  loadJsonFile(policy_file);
  initKMSType();
}

PolicyManager::~PolicyManager() {
  closeJsonHandle();
}

void PolicyManager::updatePolicy(std::string& policy_file) {
  if (json_handle_) {
    closeJsonHandle();
  }
  loadJsonFile(policy_file);
  initKMSType();
}

std::string PolicyManager::getKMSAddr() {
  std::string addr;
  if (kms_type_ != KMSType::None) {
    auto addr_cstr = cJSON_GetStringValue(cJSON_GetObjectItem(json_handle_, "addr"));
    addr = addr_cstr;
  } else {
    addr = "";
    std::cout << "Server Address is not needed when KMS type is None." << std::endl;
  }
  return addr;
}

std::string PolicyManager::getAppToken(std::string& mr_enclave) {
  auto app_list = cJSON_GetObjectItem(json_handle_, "app_list");
  auto apps_num = cJSON_GetArraySize(app_list);
  for (int i = 0; i < apps_num; i++) {
    auto app = cJSON_GetArrayItem(app_list, i);
    if (cmpItem(cJSON_GetObjectItem(app, "mr_enclave"), mr_enclave.c_str())) {
      std::string token(cJSON_GetStringValue(cJSON_GetObjectItem(app, "app_token")));
      return token;
    }
  }
  std::cout << "Error: mr_enclave[" << mr_enclave << "] not found." << std::endl;
  exit(1);
}

std::string PolicyManager::getSecretPath(
  std::string& mr_enclave, std::string& secret_name) {
  auto app_list = cJSON_GetObjectItem(json_handle_, "app_list");
  auto apps_num = cJSON_GetArraySize(app_list);
  for (int i = 0; i < apps_num; i++) {
    auto app = cJSON_GetArrayItem(app_list, i);
    if (cmpItem(cJSON_GetObjectItem(app, "mr_enclave"), mr_enclave.c_str())) {
      auto secrets = cJSON_GetObjectItem(app, "secrets");
      auto secret_path = cJSON_GetObjectItem(secrets, secret_name.c_str());
      if (secret_path == nullptr) {
        std::cout << "Error: secret[" << secret_name << "] not found." << std::endl;
        exit(1);
      } else {
        return cJSON_GetStringValue(secret_path);
      }
    }
  }
  std::cout << "Error: mr_enclave[" << mr_enclave << "] not found." << std::endl;
  exit(1);
}

std::map<std::string, std::string> PolicyManager::getSecretPathList(
  std::string& mr_enclave) {
  std::map<std::string, std::string> secret_path_list;
  auto app_list = cJSON_GetObjectItem(json_handle_, "app_list");
  auto apps_num = cJSON_GetArraySize(app_list);
  for (int i = 0; i < apps_num; i++) {
    auto app = cJSON_GetArrayItem(app_list, i);
    if (cmpItem(cJSON_GetObjectItem(app, "mr_enclave"), mr_enclave.c_str())) {
      auto secrets = cJSON_GetObjectItem(app, "secrets");
      auto secret_num = cJSON_GetArraySize(secrets);
      for (int j = 0; j < secret_num; j++) {
        auto obj = cJSON_GetArrayItem(secrets, j);
        secret_path_list[obj->string] = obj->valuestring;
      }
      return secret_path_list;
    }
  }
  std::cout << "Error: mr_enclave[" << mr_enclave << "] not found." << std::endl;
  exit(1);
}

std::shared_ptr<KMSAgent> PolicyManager::createKMSAgent(std::string& mr_enclave) {
  auto secret_list = getSecretPathList(mr_enclave);
  switch (kms_type_)
  {
  case KMSType::None:
    return std::make_shared<RawAgent>(secret_list);
    break;
  case KMSType::Vault: {
    auto addr = getKMSAddr();
    auto token = getAppToken(mr_enclave);
    return std::make_shared<VaultAgent>(addr, token, secret_list);
    break;
  }
  case KMSType::eHSM:
    std::cout << "Not implemented." << std::endl;
    break;
  default:
    std::cout << "Unsupported KMS type!" << std::endl;
    exit(1);
  }
}

void PolicyManager::loadJsonFile(std::string& file_name) {
  auto file_ptr = fopen(file_name.c_str(), "r");
  if (!file_ptr) {
    std::cout << "Can't open " << file_name << std::endl;
    exit(1);
  }
  fseek(file_ptr, 0, SEEK_END);
  auto length = ftell(file_ptr);
  fseek(file_ptr, 0, SEEK_SET);
  auto buffer = malloc(length);
  fread(buffer, 1, length, file_ptr);
  fclose(file_ptr);

  json_handle_ = cJSON_Parse((const char *)buffer);
  free(buffer);
  buffer = nullptr;

  if (!json_handle_) {
    std::cout << "cjson open " << file_name
              << " error: " << cJSON_GetErrorPtr() << std::endl;
  }
}

void PolicyManager::closeJsonHandle() {
  if (json_handle_) {
    cJSON_Delete(json_handle_);
    json_handle_ = nullptr;
  }
}

bool PolicyManager::cmpItem(cJSON* obj, const char* item) {
    auto obj_item = cJSON_Print(obj);
    return strncmp(obj_item+1, item, std::min(strlen(item), strlen(obj_item)-2)) == 0;
}

void PolicyManager::initKMSType() {
  auto kms_type = cJSON_GetStringValue(cJSON_GetObjectItem(json_handle_, "kms"));
  if (strcmp(kms_type, "none") == 0) {
    kms_type_ = KMSType::None;
  } else if (strcmp(kms_type, "vault") == 0) {
    kms_type_ = KMSType::Vault;
  } else if (strcmp(kms_type, "ehsm")) {
    kms_type_ = KMSType::eHSM;
  } else {
    std::cout << "Error: unsupported KMS backend." << std::endl;
    exit(1);
  }
}
}