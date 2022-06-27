
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include "seal/seal.h"
#include "utils.hpp"
#include "infer_client.hpp"
#include "infer_server.hpp"

InferClient::InferClient(HEParam& param) {
  initContext(param);
}

void InferClient::initContext(HEParam& param) {
  // SEAL uses an additional 'special prime' coeff modulus for relinearization
  // only. As such, encrypting with N coeff moduli yields a ciphertext with
  // N-1 coeff moduli for computation. See section 2.2.1 in
  // https://arxiv.org/pdf/1908.04172.pdf. So, we add an extra prime for fair
  // comparison against other HE schemes.

  seal::EncryptionParameters seal_params{seal::scheme_type::ckks};
  seal_params.set_poly_modulus_degree(param.poly_modulus_degree_);

  seal_params.set_coeff_modulus(
    seal::CoeffModulus::Create(param.poly_modulus_degree_, param.coeff_modulus_));

  context_.reset(new seal::SEALContext(seal_params, true, param.sec_level_));
  auto keygen = std::make_shared<seal::KeyGenerator>(*context_);
  keygen->create_public_key(public_key_);
  secret_key_ = keygen->secret_key();
  keygen->create_relin_keys(relin_keys_);
  keygen->create_galois_keys(galois_keys_);

  encryptor_ = std::make_shared<seal::Encryptor>(*context_, public_key_);
  decryptor_ = std::make_shared<seal::Decryptor>(*context_, secret_key_);
  encoder_ = std::make_shared<seal::CKKSEncoder>(*context_);
  slot_count_ = encoder_->slot_count();
  scale_ = param.scale_;
}

void InferClient::loadDataSet(std::string& file_name) {
  if (!file_exists(file_name)) throw std::runtime_error(file_name + " not found");

  std::ifstream ifs(file_name);

  std::vector<std::vector<std::string>> rawdata = readCSV(ifs);
  std::vector<std::vector<double>> input_data(rawdata.size() - 1);

  for (size_t i = 1; i < rawdata.size(); i++) {
    std::transform(rawdata[i].begin(), rawdata[i].end(),
                   std::back_inserter(input_data[i - 1]),
                   [](const std::string& val) { return std::stod(val); });
  }
  auto n_sample = input_data.size();
  eval_data_.resize(n_sample);
  eval_target_.resize(n_sample);
  for (size_t i = 0; i < n_sample; i++) {
    eval_data_[i] = std::vector<double>(input_data[i].begin(), input_data[i].end() - 1);
    eval_target_[i] = *(input_data[i].end() - 1);
  }
  // test
  for (auto item : eval_data_[0]) {
    std::cout << item << " ";
  }
  std::cout << std::endl;
  std::cout << eval_target_[0] << std::endl;
  // test
}

void InferClient::encodeEncryptData() {
  int n_samples = eval_data_.size();
  if (n_samples < 1) throw std::invalid_argument("Input data is empty");
  
  size_t total_batch =
      n_samples / slot_count_ + (n_samples % slot_count_ == 0 ? 0 : 1);
  size_t last_batch_size =
      n_samples % slot_count_ == 0 ? slot_count_ : n_samples % slot_count_;
  std::cout << "Batche num: " << total_batch << "      Batch size: " << slot_count_ << std::endl;
    
  // Transpose Data
  std::vector<std::vector<std::vector<double>>> batched_data_T(total_batch);

#pragma omp parallel for num_threads(OMPUtilitiesS::getThreadsAtLevel())
  for (size_t i = 0; i < total_batch; ++i) {
    size_t batchsize = i < total_batch - 1 ? slot_count_ : last_batch_size;
    auto first = eval_data_.begin() + i * slot_count_;
    batched_data_T[i] =
        std::vector<std::vector<double>>(first, first + batchsize);
    batched_data_T[i] = transpose(batched_data_T[i]);
  }

  // Encode and Encrypt Data
  std::vector<std::vector<seal::Ciphertext>> ct_inputs;
  std::vector<std::vector<seal::Plaintext>> pt_inputs;
  size_t n_features = batched_data_T[0].size();

  encrypted_data_.resize(total_batch);
  for (int i = 0; i < encrypted_data_.size(); ++i) {
    encrypted_data_[i].resize(n_features);
  }

#pragma omp parallel for collapse(2) \
    num_threads(OMPUtilitiesS::getThreadsAtLevel())
  for (size_t i = 0; i < total_batch; ++i)
    for (size_t j = 0; j < n_features; ++j)
      encrypted_data_[i][j] = encrypt(encode(
          gsl::span(batched_data_T[i][j].data(), batched_data_T[i][j].size())));
}

std::vector<double> InferClient::decryptDecodeResult(
  std::vector<seal::Ciphertext>& encrypted_result) {
  int n_samples = eval_data_.size();
  size_t n_batches = encrypted_result.size();
  std::vector<double> ret(n_batches * slot_count_);

#pragma omp parallel for num_tCODE_SRCShreads(OMPUtilitiesS::getThreadsAtLevel())
  for (size_t i = 0; i < n_batches; ++i) {
    seal::Plaintext pt_buf;
    decryptor_->decrypt(encrypted_result[i], pt_buf);
    std::vector<double> buf;
    encoder_->decode(pt_buf, buf);
    std::copy_n(buf.begin(), slot_count_, &ret[i * slot_count_]);
  }

  return std::vector<double>(ret.begin(), ret.begin() + n_samples);
}

seal::Plaintext InferClient::encode(const gsl::span<const double>& v) {
  if (v.size() > slot_count_)
    throw std::invalid_argument(
        "Input vector size is larger than slot_count");

  seal::Plaintext pt_ret;
  encoder_->encode(v, scale_, pt_ret);
  return pt_ret;
}

seal::Ciphertext InferClient::encrypt(const seal::Plaintext& v) {
  seal::Ciphertext ct_ret;
  encryptor_->encrypt(v, ct_ret);
  return ct_ret;
}

int main(int argc, char** argv) {
  auto param = HEParam();
  auto client = InferClient(param);
  std::string dataset("../datasets/lrtest_mid_eval.csv");
  client.loadDataSet(dataset);
  client.encodeEncryptData();

  std::string model_file("../datasets/lrtest_mid_lrmodel.csv");
  auto server = InferServer();
  auto context = client.getContext();
  auto scale = client.getScale();
  auto relin_keys = client.getRelinKeys();
  auto pub_key = client.getPubKey();
  server.initContext(context, pub_key, relin_keys, scale);
  server.loadWeights(model_file);
  auto encrypted_data = client.getEncryptedData();
  // auto encrypted_result = server.inference(encrypted_data);
  auto result = client.decryptDecodeResult(encrypted_data[0]);
  for (int i = 0; i < 10; i++) {
    std::cout << result[i] << " ";
  }
  std::cout << std::endl;
  // compareResult();
  return 0;
}
