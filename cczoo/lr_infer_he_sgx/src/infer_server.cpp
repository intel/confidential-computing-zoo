#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include "seal/seal.h"
#include "utils.hpp"
#include "infer_server.hpp"

void InferServer::initContext(seal::SEALContext& context,
  seal::PublicKey& public_key, seal::RelinKeys& relin_keys, int scale) {
  context_ = std::make_shared<seal::SEALContext>(context);
  encryptor_ = std::make_shared<seal::Encryptor>(context, public_key);
  evaluator_ = std::make_shared<seal::Evaluator>(context);
  encoder_ = std::make_shared<seal::CKKSEncoder>(context);
  slot_count_ = encoder_->slot_count();
  scale_ = scale;
  relin_keys_ = relin_keys;
}

void InferServer::loadWeights(std::string& model_file) {
  // Load Raw Weights
  if (!file_exists(model_file)) throw std::runtime_error(model_file + " not found");
  std::ifstream ifs(model_file);

  std::vector<std::vector<std::string>> rawdata = readCSV(ifs);
  std::vector<std::vector<double>> rawweights(rawdata.size());

  for (size_t i = 0; i < rawdata.size(); i++) {
    std::transform(rawdata[i].begin(), rawdata[i].end(),
                   std::back_inserter(rawweights[i]),
                   [](const std::string& val) { return std::stod(val); });
  }
  // Encode Weights and Bias
  auto weights = std::vector<double>(rawweights[0].begin() + 1, rawweights[0].end());
  auto bias = rawweights[0][0];
  size_t n_features = weights.size();
  encoded_weights_.resize(n_features);

  #pragma omp parallel for num_threads(OMPUtilitiesS::getThreadsAtLevel())
  for (size_t i = 0; i < n_features; ++i)
    encoded_weights_[i] = encode(gsl::span(
        std::vector<double>(slot_count_, weights[i]).data(), slot_count_));
  
  encoded_bias_ = encode(
    gsl::span(std::vector<double>(slot_count_, bias).data(), slot_count_));
}

std::vector<seal::Ciphertext> InferServer::inference(
  std::vector<std::vector<seal::Ciphertext>>& encrypted_data) {
  auto total_batch = encrypted_data.size();
  std::vector<seal::Ciphertext> ct_ret(total_batch);

  #pragma omp parallel for num_threads(OMPUtilitiesS::getThreadsAtLevel())

  for (int i = 0; i < total_batch; ++i) {
    ct_ret[i] = evaluateLRTransposed(encrypted_data[i]);
  }
  return ct_ret;
}

seal::Plaintext InferServer::encode(const gsl::span<const double>& v) {
  if (v.size() > slot_count_)
    throw std::invalid_argument(
        "Input vector size is larger than slot_count");

  seal::Plaintext pt_ret;
  encoder_->encode(v, scale_, pt_ret);
  return pt_ret;
}

seal::Ciphertext InferServer::encrypt(const seal::Plaintext& v) {
  seal::Ciphertext ct_ret;
  encryptor_->encrypt(v, ct_ret);
  return ct_ret;
}

seal::Ciphertext InferServer::evaluateLRTransposed(
    std::vector<seal::Ciphertext>& encrypted_data) {
  // W * X
  seal::Ciphertext retval = vecMatProduct(encoded_weights_, encrypted_data);

  matchLevel(&retval, &encoded_bias_);
  encoded_bias_.scale() = scale_;
  retval.scale() = scale_;

  // Add Bias
  evaluator_->add_plain_inplace(retval, encoded_bias_);

  // Sigmoid
  retval = evaluatePolynomialVector(retval, gsl::span(sigmoid_coeff_3, 4));
  return retval;
}

seal::Ciphertext InferServer::vecMatProduct(
    const std::vector<seal::Plaintext>& A_T_extended,
    const std::vector<seal::Ciphertext>& B) {
  size_t rows = A_T_extended.size();

  std::vector<seal::Ciphertext> retval(rows);
  std::cout << "2222" << std::endl;
#pragma omp parallel for num_threads(OMPUtilitiesS::getThreadsAtLevel())
  for (size_t r = 0; r < rows; ++r) {
    evaluator_->multiply_plain(B[r], A_T_extended[r], retval[r]);
  }
  // add all rows
  size_t step = 2;
  while ((step / 2) < rows) {
#pragma omp parallel for num_threads(OMPUtilitiesS::getThreadsAtLevel())
    for (size_t i = 0; i < rows; i += step) {
      if ((i + step / 2) < rows)
        evaluator_->add_inplace(retval[i], retval[i + step / 2]);
    }
    step *= 2;
  }

  evaluator_->rescale_to_next_inplace(retval[0]);

  return retval[0];
}

void InferServer::matchLevel(seal::Ciphertext* a, seal::Plaintext* b) const {
  int a_level = getLevel(*a);
  int b_level = getLevel(*b);
  if (a_level > b_level)
    evaluator_->mod_switch_to_inplace(*a, b->parms_id());
  else if (a_level < b_level)
    evaluator_->mod_switch_to_inplace(*b, a->parms_id());
}

void InferServer::matchLevel(seal::Ciphertext* a, seal::Ciphertext* b) const {
  int a_level = getLevel(*a);
  int b_level = getLevel(*b);
  if (a_level > b_level)
    evaluator_->mod_switch_to_inplace(*a, b->parms_id());
  else if (a_level < b_level)
    evaluator_->mod_switch_to_inplace(*b, a->parms_id());
}

// Returns the level of the ciphertext
size_t InferServer::getLevel(const seal::Ciphertext& cipher) const {
  return context_->get_context_data(cipher.parms_id())->chain_index();
}

// Returns the level of the plaintext
size_t InferServer::getLevel(const seal::Plaintext& plain) const {
  return context_->get_context_data(plain.parms_id())->chain_index();
}

seal::Ciphertext InferServer::evaluatePolynomialVector(
    const seal::Ciphertext& inputs, const gsl::span<const double>& coefficients,
    bool is_minus) {
  if (coefficients.empty())
    throw std::invalid_argument("coefficients cannot be empty");

  double multiplier = (is_minus) ? -1.0 : 1.0;

  seal::Ciphertext retval = encrypt(encode(gsl::span(
      std::vector<double>(slot_count_, multiplier * coefficients[0]).data(),
      slot_count_)));

  size_t degree = coefficients.size() - 1;

  seal::Ciphertext x_ref = inputs;
  seal::Ciphertext powx = inputs;
  for (size_t d = 1; d <= degree; ++d) {
    if (d > 1) {
      evaluator_->multiply_inplace(powx, x_ref);
      evaluator_->relinearize_inplace(powx, relin_keys_);
      evaluator_->rescale_to_next_inplace(powx);
      matchLevel(&x_ref, &powx);
    }

    if (coefficients[d] != 0.0) {
      seal::Plaintext pt_coeff = encode(gsl::span(
          std::vector<double>(slot_count_, multiplier * coefficients[d])
              .data(),
          slot_count_));
      seal::Ciphertext buf;

      matchLevel(&powx, &pt_coeff);
      evaluator_->multiply_plain(powx, pt_coeff, buf);
      evaluator_->rescale_to_next_inplace(buf);

      matchLevel(&retval, &buf);
      buf.scale() = scale_;
      evaluator_->add_inplace(retval, buf);
    }
  }

  return retval;
}
// int main(int argc, char** argv) {
//   return 0;
// }

