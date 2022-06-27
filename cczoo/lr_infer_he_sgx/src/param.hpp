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