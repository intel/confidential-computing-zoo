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

#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include "gflags/gflags.h"
#include "seal/seal.h"
#include "utils.hpp"
#include "infer_client.hpp"
#include "infer_server.hpp"

DEFINE_string(
    data, "lrtest_mid_eval.csv", "Data file to test.");

DEFINE_int32(poly_modulus_degree, 8192,
             "Set polynomial modulus for CKKS context. Determines the batch "
             "size and security level, thus recommended size is 4096-16384. "
             "Must be a power of 2, with the range of [1024, 32768]");

DEFINE_int32(security_level, 0, "Security level. One of [0, 128, 192, 256].");

DEFINE_string(coeff_modulus, "60,45,45,45,45,60",
              "Coefficient modulus (list of primes). The bit-lengths of the "
              "primes to be generated.");

DEFINE_int32(batch_size, 0,
             "Batch size. 0 = automatic (poly_modulus_degree / 2). Max = "
             "poly_modulus_degree / 2.");

DEFINE_int32(scale, 45, "Scaling parameter defining precision.");

InferClient::InferClient(HEParam& param, std::shared_ptr<Channel> channel) 
: stub_(Inference::NewStub(channel)) {
  initContext(param);
}

void InferClient::initContext(HEParam& param) {
  seal::EncryptionParameters seal_params(seal::scheme_type::ckks);
  seal_params.set_poly_modulus_degree(param.poly_modulus_degree_);
  seal_params.set_coeff_modulus(
    seal::CoeffModulus::Create(param.poly_modulus_degree_, param.coeff_modulus_));
  sec_level_ = param.sec_level_;
  context_.reset(new seal::SEALContext(seal_params, true, param.sec_level_));
  enc_params_ = seal_params;
  auto keygen = std::make_shared<seal::KeyGenerator>(*context_);
  keygen->create_public_key(public_key_);
  secret_key_ = keygen->secret_key();
  keygen->create_relin_keys(relin_keys_);

  encryptor_ = std::make_shared<seal::Encryptor>(*context_, public_key_);
  decryptor_ = std::make_shared<seal::Decryptor>(*context_, secret_key_);
  encoder_ = std::make_shared<seal::CKKSEncoder>(*context_);
  slot_count_ = encoder_->slot_count();
  scale_ = 1UL << param.scale_;
}

void InferClient::loadDataSet(std::string& file_name) {
  if (!fileExists(file_name)) throw std::runtime_error(file_name + " not found");

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
}

void InferClient::encodeEncryptData() {
  int n_samples = eval_data_.size();
  if (n_samples < 1) throw std::invalid_argument("Input data is empty");
  
  size_t total_batch =
      n_samples / slot_count_ + (n_samples % slot_count_ == 0 ? 0 : 1);
  size_t last_batch_size =
      n_samples % slot_count_ == 0 ? slot_count_ : n_samples % slot_count_;

  // Transpose Data
  std::vector<std::vector<std::vector<double>>> batched_data_T(total_batch);

  for (size_t i = 0; i < total_batch; ++i) {
    size_t batchsize = i < total_batch - 1 ? slot_count_ : last_batch_size;
    auto first = eval_data_.begin() + i * slot_count_;
    batched_data_T[i] =
        std::vector<std::vector<double>>(first, first + batchsize);
    batched_data_T[i] = transpose(batched_data_T[i]);
  }

  // Encode and Encrypt Data
  size_t n_features = batched_data_T[0].size();

  encrypted_data_.resize(total_batch);
  for (int i = 0; i < encrypted_data_.size(); ++i) {
    encrypted_data_[i].resize(n_features);
  }

  for (size_t i = 0; i < total_batch; ++i)
    for (size_t j = 0; j < n_features; ++j)
      encrypted_data_[i][j] = encrypt(encode(
          gsl::span(batched_data_T[i][j].data(), batched_data_T[i][j].size())));
}

bool InferClient::initServerCtx() {
  std::stringstream params_stream;
  std::stringstream pubkey_stream;
  std::stringstream relinkey_stream;
  InitCtxRequest request;
  InitCtxReply reply;
  size_t trans_size;
  trans_size = enc_params_.save(params_stream, seal::compr_mode_type::zstd);
  std::cout << "EncryptionParameters: wrote " << trans_size << " bytes" << std::endl;
  trans_size = public_key_.save(pubkey_stream, seal::compr_mode_type::zstd);
  std::cout << "PublicKey: wrote " << trans_size << " bytes" << std::endl;
  trans_size = relin_keys_.save(relinkey_stream, seal::compr_mode_type::zstd);
  std::cout << "RelinKeys: wrote " << trans_size << " bytes" << std::endl;
  request.set_params(params_stream.str());
  request.set_pub_key(pubkey_stream.str());
  request.set_relin_key(relinkey_stream.str());
  request.set_security_level(static_cast<int>(sec_level_));
  request.set_scale(scale_);
  ClientContext context;
  auto status = stub_->InitCtx(&context, request, &reply);
  if (!status.ok()) {
    std::cout << status.error_code() << ": " << status.error_message()
              << std::endl;
    return false;
  }
  return true;
}

std::vector<seal::Ciphertext> InferClient::infer() {
  std::stringstream data_stream;
  std::stringstream result_stream;
  auto batch_size = encrypted_data_[0].size();
  auto batches = encrypted_data_.size();
  for (auto i = 0; i < batches; i++) {
    for (auto j = 0; j < batch_size; j++) {
      encrypted_data_[i][j].save(data_stream, seal::compr_mode_type::zstd);
    }
  }
  InferRequest request;
  InferReply reply;
  request.set_data(data_stream.str());
  request.set_batches(batches);
  request.set_batch_size(batch_size);
  ClientContext context;
  auto status = stub_->Infer(&context, request, &reply);
  if (!status.ok()) {
    std::stringstream error_msg;
    error_msg << status.error_code() << ": " << status.error_message()
              << std::endl;
    throw std::runtime_error(error_msg.str());
  } else {
    auto counts = reply.counts();
    result_stream << reply.result();
    std::vector<seal::Ciphertext> infer_results(counts);
    for (auto i = 0; i < counts; i++) {
      infer_results[i].load(*context_, result_stream);
    }
    return infer_results;
  }
}

std::vector<double> InferClient::decryptDecodeResult(
  std::vector<seal::Ciphertext>& encrypted_result) {
  int n_samples = eval_data_.size();
  size_t n_batches = encrypted_result.size();
  std::vector<double> ret(n_batches * slot_count_);

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
  gflags::ParseCommandLineFlags(&argc, &argv, true);
  HEParam param(FLAGS_poly_modulus_degree, FLAGS_security_level,
                FLAGS_coeff_modulus, FLAGS_batch_size, FLAGS_scale);
  auto client = InferClient(param, grpc::CreateChannel(
      "localhost:50051", grpc::InsecureChannelCredentials()));
  // std::string fullpath(__FILE__);
  // std::string src_dir = fullpath.substr(0, fullpath.find_last_of("\\/"));
  // std::string datafile(src_dir + "/../datasets/" + FLAGS_data + "_eval.csv");
  client.loadDataSet(FLAGS_data);
  client.encodeEncryptData();

  client.initServerCtx();
  auto encrypted_result = client.infer();

  auto result = client.decryptDecodeResult(encrypted_result);

  std::transform(result.begin(), result.end(), result.begin(),
    [](const double& val) { return static_cast<int>(0.5 + val); });

  auto eval_target = client.getEvalTarget();
  auto eval = getEvalmetrics(eval_target, result);
  std::cout << "HE inference result - accuracy: " << eval["acc"] << std::endl;

  return 0;
}
