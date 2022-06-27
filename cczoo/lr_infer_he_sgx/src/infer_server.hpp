#ifndef INFER_SERVER_HPP_
#define INFER_SERVER_HPP_

// #include <grpcpp/grpcpp.h>
#include "seal/seal.h"

const double sigmoid_coeff_3[] = {0.5, 0.15012, 0.0, -0.001593008};

class InferServer {
public:
void initContext(seal::SEALContext& context, seal::PublicKey& public_key,
  seal::RelinKeys& relin_keys, int scale);
void loadWeights(std::string& model_file);
std::vector<seal::Ciphertext> inference(
  std::vector<std::vector<seal::Ciphertext>>& encrypted_data);
private:
  seal::Plaintext encode(const gsl::span<const double>& v);
  seal::Ciphertext encrypt(const seal::Plaintext& v); 
  seal::Ciphertext evaluateLRTransposed(
    std::vector<seal::Ciphertext>& encrypted_data);
  seal::Ciphertext vecMatProduct(
    const std::vector<seal::Plaintext>& A_T_extended,
    const std::vector<seal::Ciphertext>& B);
  void matchLevel(seal::Ciphertext* a, seal::Plaintext* b) const;
  void matchLevel(seal::Ciphertext* a, seal::Ciphertext* b) const;
  size_t getLevel(const seal::Ciphertext& cipher) const;
  size_t getLevel(const seal::Plaintext& plain) const;
  seal::Ciphertext evaluatePolynomialVector(
    const seal::Ciphertext& inputs, const gsl::span<const double>& coefficients,
    bool is_minus = false);
  seal::RelinKeys relin_keys_;
  std::shared_ptr<seal::SEALContext> context_;
  std::shared_ptr<seal::CKKSEncoder> encoder_;
  std::shared_ptr<seal::Encryptor> encryptor_;
  std::shared_ptr<seal::Evaluator> evaluator_;
  std::vector<seal::Plaintext> encoded_weights_;
  seal::Plaintext encoded_bias_;
  size_t slot_count_;
  int scale_;
};
#endif // INFER_SERVER_HPP_
