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
#include "cpr/cpr.h"
#include "cjson/cJSON.h"
#include "kms_agent.hpp"

namespace as {
std::string RawAgent::getSecret(std::string& secret_name) {
  return secret_map_[secret_name];
}

std::string VaultAgent::getSecret(std::string& secret_name) {
  auto endpoint = secret_map_[secret_name];
  std::string url = addr_ + "/v1/" + endpoint;
  std::cout << url << std::endl;
  cpr::Response r = cpr::Get(cpr::Url{url}, cpr::Bearer{token_});
  if (r.status_code != 200) {
    std::cout << "Error: failed to get secret! (status code: " << r.status_code  << ")" << std::endl;
    exit(1);
  }
  auto json_root = cJSON_Parse(r.text.c_str());
  auto key_obj = cJSON_GetObjectItem((cJSON_GetObjectItem(json_root, "data")), "key");
  if (!key_obj) {
    std::cout << "Error: json object not found!" << std::endl;
    exit(1);
  }
  return cJSON_GetStringValue(key_obj);
}
}
