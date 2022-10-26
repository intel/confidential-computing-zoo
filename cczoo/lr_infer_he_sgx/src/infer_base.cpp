// Copyright (c) 2022 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
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

#include <sys/stat.h>
#include <iostream>
#include "infer_base.hpp"

bool InferBase::fileExists(const std::string& fn) {
  struct stat buffer;
  return (stat(fn.c_str(), &buffer) == 0);
}

std::vector<std::string> InferBase::readCSVRow(const std::string& row) {
  CSVState state = CSVState::UnquotedField;
  std::vector<std::string> fields{""};
  size_t i = 0;  // index of the current field
  for (char c : row) {
    switch (state) {
      case CSVState::UnquotedField:
        switch (c) {
          case ',':  // end of field
            fields.push_back("");
            i++;
            break;
          case '"':
            state = CSVState::QuotedField;
            break;
          default:
            fields[i].push_back(c);
            break;
        }
        break;
      case CSVState::QuotedField:
        switch (c) {
          case '"':
            state = CSVState::QuotedQuote;
            break;
          default:
            fields[i].push_back(c);
            break;
        }
        break;
      case CSVState::QuotedQuote:
        switch (c) {
          case ',':  // , after closing quote
            fields.push_back("");
            i++;
            state = CSVState::UnquotedField;
            break;
          case '"':  // "" -> "
            fields[i].push_back('"');
            state = CSVState::QuotedField;
            break;
          default:  // end of quote
            state = CSVState::UnquotedField;
            break;
        }
        break;
    }
  }
  return fields;
}

std::vector<std::vector<std::string>> InferBase::readCSV(std::istream& in) {
  std::vector<std::vector<std::string>> table;
  std::string row;
  while (!in.eof()) {
    std::getline(in, row);
    if (in.bad() || in.fail()) {
      break;
    }
    auto fields = readCSVRow(row);
    table.push_back(fields);
  }
  return table;
}

std::vector<std::vector<double>> InferBase::transpose(
    const std::vector<std::vector<double>>& data) {
  std::vector<std::vector<double>> res(data[0].size(),
                                       std::vector<double>(data.size()));

#pragma omp parallel for collapse(2) \
    num_threads(OMPUtilitiesS::getThreadsAtLevel())
  for (size_t i = 0; i < data[0].size(); i++) {
    for (size_t j = 0; j < data.size(); j++) {
      res[i][j] = data[j][i];
    }
  }
  return res;
}