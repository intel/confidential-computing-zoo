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

#include <algorithm>
#include <iostream>
#include <numeric>
#include <cmath>
#include <stdexcept>
#include <unistd.h>
#include "utils.hpp"

std::map<std::string, double> getEvalmetrics(
    const std::vector<double>& expected, const std::vector<double>& predicted) {
  if (expected.size() != predicted.size())
    throw std::invalid_argument("Expected and Predicted size mismatch");

  std::map<std::string, double> retval;
  double tp = 0, tn = 0, fp = 0, fn = 0;

  for (size_t i = 0; i < expected.size(); ++i) {
    if (expected[i] == 1.0 && predicted[i] == 1.0)
      tp++;
    else if (expected[i] == 1 && predicted[i] == 0.0)
      fn++;
    else if (expected[i] == 0 && predicted[i] == 1.0)
      fp++;
    else
      tn++;
  }

  retval["acc"] = (tp + tn) / (tp + fp + tn + fn);
  if (tp + fp > 0)
    retval["precision"] = tp / (tp + fp);
  else
    retval["precision"] = 0.0;

  if (tp + fn > 0)
    retval["recall"] = tp / (tp + fn);
  else
    retval["recall"] = 0.0;

  if (retval["precision"] + retval["recall"] == 0)
    retval["f1"] = 0.0;
  else
    retval["f1"] = (retval["precision"] * retval["recall"]) /
                   (retval["precision"] + retval["recall"]);

  return retval;
}

void doCompare(std::vector<double>& expected, std::vector<double>& predicted) {
  int n_samples = expected.size();
  if (predicted.size() != n_samples) {
    throw std::runtime_error("The sizes of two sets for comparison must be same.");
  }
  int mismatch_ct = 0;
  for (size_t j = 0; j < n_samples; ++j) {
    if (predicted[j] != expected[j]) {
      mismatch_ct++;
    }
  }
  if (mismatch_ct > 0) {
    std::cout << "Mismatch count with cleartext LR: "
              << mismatch_ct << "/" << n_samples << std::endl;
  } else {
    std::cout << "All match!" << std::endl;
  }
}
