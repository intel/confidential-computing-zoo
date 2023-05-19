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
#ifndef _KMS_AGENT_HPP_
#define _KMS_AGENT_HPP_

namespace as {
enum KMSType {
  Vault,
  eHSM,
  None
};

class KMSAgent {
public:
virtual std::string getSecret(std::string& secret_name) = 0;
};

class RawAgent : public KMSAgent {
public:
RawAgent(std::map<std::string, std::string>& secret_path_list) 
: secret_map_(secret_path_list) {
}
std::string getSecret(std::string& secret_name) override;
private:
std::map<std::string, std::string> secret_map_;
};

class VaultAgent : public KMSAgent {
public:
VaultAgent(std::string& addr, std::string& token,
           std::map<std::string, std::string>& secret_path_list) 
: addr_(addr), token_(token), secret_map_(secret_path_list) {}
std::string getSecret(std::string& secret_name) override;
private:
std::string addr_;
std::string token_;
std::map<std::string, std::string> secret_map_;
};
}
#endif  // _KMS_AGENT_HPP_
