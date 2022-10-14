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

#include "param.hpp"

HEParam::HEParam(int poly_modulus_degree, int security_level,
  std::string coeff_modulus, int batch_size, int scale) {
  scale_ = scale;
  if (poly_modulus_degree < 1024 || poly_modulus_degree > 32768 ||
      (poly_modulus_degree & (poly_modulus_degree - 1)) != 0)
  throw std::invalid_argument(
      "poly_modulus_degree must be power of 2 and within [1024, 32768] "
      "range.");
  poly_modulus_degree_ = poly_modulus_degree;

  if (batch_size < 0 || batch_size > poly_modulus_degree / 2)
    throw std::invalid_argument(
        "batch_size must be between 0 and poly_modulus_degree / 2.");
  batch_size_ = batch_size;

  switch (security_level) {
    case 0:
      sec_level_ = seal::sec_level_type::none;
      break;
    case 128:
      sec_level_ = seal::sec_level_type::tc128;
      break;
    case 192:
      sec_level_ = seal::sec_level_type::tc192;
      break;
    case 256:
      sec_level_ = seal::sec_level_type::tc256;
      break;
    default:
      throw std::invalid_argument(
        "ERROR: Security level must be one of [0, 128, 192, 256].");
  }

  std::stringstream ss(coeff_modulus);
  for (int i; ss >> i;) {
    coeff_modulus_.push_back(i);
    if (ss.peek() == ',') ss.ignore();
  }
};