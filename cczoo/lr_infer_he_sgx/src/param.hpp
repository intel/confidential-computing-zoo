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

#ifndef PARAM_HPP_
#define PARAM_HPP_

#include "seal/seal.h"

class HEParam {
public:
  HEParam(int poly_modulus_degree = 8192, int security_level = 0,
    std::string coeff_modulus = "60,45,45,45,45,60", int batch_size = 0,
    int scale = 45);
  int poly_modulus_degree_;
  seal::sec_level_type sec_level_;
  std::vector<int> coeff_modulus_;
  int batch_size_;
  int scale_;
};

#endif  // PARAM_HPP_