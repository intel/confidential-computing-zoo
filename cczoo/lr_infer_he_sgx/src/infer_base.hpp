// Copyright (c) 2022 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifndef INFER_BASE_HPP_
#define INFER_BASE_HPP_

#include <vector>
#include <string>

enum class CSVState { UnquotedField, QuotedField, QuotedQuote };

class InferBase {
public:
  bool fileExists(const std::string& fn);
  std::vector<std::string> readCSVRow(const std::string& row);
  std::vector<std::vector<std::string>> readCSV(std::istream& in);
  std::vector<std::vector<double>> transpose(
    const std::vector<std::vector<double>>& data);
};

#endif  // INFER_BASE_HPP_
