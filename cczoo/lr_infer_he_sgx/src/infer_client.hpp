#ifndef INFER_CLIENT_HPP_
#define INFER_CLIENT_HPP_

// #include <grpcpp/grpcpp.h>
#include "param.hpp"

class InferClient {
public:
  InferClient(HEParam& param);
  void initContext(HEParam& param);
  void loadDataSet(std::string& file_name);
  void encodeEncryptData();
  std::vector<double> decryptDecodeResult(
    std::vector<seal::Ciphertext>& encrypted_result);
  
  // temp func
  seal::SEALContext getContext() {
    return *context_;
  }
  std::vector<std::vector<seal::Ciphertext>> getEncryptedData() {
    return encrypted_data_;
  }
  int getScale() {
    return scale_;
  }
  seal::RelinKeys getRelinKeys() {
    return relin_keys_;
  }
  seal::PublicKey getPubKey() {
    return public_key_;
  }
  // temp func
private:
  seal::Plaintext encode(const gsl::span<const double>& v);
  seal::Ciphertext encrypt(const seal::Plaintext& v);
  std::shared_ptr<seal::SEALContext> context_;
  seal::PublicKey public_key_;
  seal::SecretKey secret_key_;
  seal::RelinKeys relin_keys_;
  seal::GaloisKeys galois_keys_;
  std::shared_ptr<seal::Encryptor> encryptor_;
  std::shared_ptr<seal::Decryptor> decryptor_;
  std::shared_ptr<seal::CKKSEncoder> encoder_;
  size_t slot_count_;
  int scale_;
  std::vector<std::vector<double>> eval_data_;
  std::vector<double> eval_target_;
  std::vector<std::vector<seal::Ciphertext>> encrypted_data_;
};
#endif // INFER_CLIENT_HPP_

