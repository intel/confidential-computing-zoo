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
#include <sstream>
#include <vector>
#include "seal/seal.h"
#include "utils.hpp"
#include "infer_server.hpp"

void InferServer::initContext(std::stringstream& params_stream,
  std::stringstream& pubkey_stream, double scale) {
  seal::EncryptionParameters params;
  params.load(params_stream);
  seal::SEALContext context = seal::SEALContext(params, true, seal::sec_level_type::none);
  seal::PublicKey public_key;
  public_key.load(context, pubkey_stream);
  auto keygen = seal::KeyGenerator(context);
  keygen.create_relin_keys(relin_keys_);

  context_ = std::make_shared<seal::SEALContext>(context);
  encryptor_ = std::make_shared<seal::Encryptor>(context, public_key);
  evaluator_ = std::make_shared<seal::Evaluator>(context);
  encoder_ = std::make_shared<seal::CKKSEncoder>(context);
  slot_count_ = encoder_->slot_count();
  scale_ = scale;

  //tmp: load weights
  std::string model_file("/home/data/lr_infer_he/cczoo/lr_infer_he_sgx/datasets/lrtest_mid_lrmodel.csv");
  loadWeights(model_file);
  //tmp
}

void InferServer::loadWeights(std::string& model_file) {
  // Load Raw Weights
  if (!fileExists(model_file)) throw std::runtime_error(model_file + " not found");
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
  std::stringstream& input, int batches, int batch_size) {
  std::vector<std::vector<seal::Ciphertext>> encrypted_data;
  encrypted_data.resize(batches);
  for (int i = 0; i < batches; i++) {
    encrypted_data[i].resize(batch_size);
  }
  for (auto i = 0; i < batches; i++) {
    for (auto j = 0; j < batch_size; j++) {
      encrypted_data[i][j].load(*context_, input);
    }
  }
  std::vector<seal::Ciphertext> ct_ret(batches);

  for (int i = 0; i < batches; ++i) {
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

Status InferServiceImpl::InitCtx(ServerContext* context,
  const InitCtxRequest* request, InitCtxReply* reply) {
  std::stringstream params_stream;
  std::stringstream pubkey_stream;
  std::stringstream relinkey_stream;
  params_stream << request->params();
  pubkey_stream << request->pub_key();
  double scale = request->scale();
  server_.initContext(params_stream, pubkey_stream, scale);
  return Status::OK;
}
Status InferServiceImpl::Infer(ServerContext* context,
  const InferRequest* request, InferReply* reply) {
  std::stringstream data_stream;
  std::stringstream result_stream;
  data_stream << request->data();
  auto batches = request->batches();
  auto batch_size =  request->batch_size();
  auto ct_result = server_.inference(data_stream, batches, batch_size);
  auto counts = ct_result.size();
  for (auto i = 0; i < counts; i++) {
    ct_result[i].save(result_stream);
  }
  reply->set_result(result_stream.str());
  reply->set_counts(counts);
  return Status::OK;
};

void RunServer() {
  std::string server_address("localhost:50051");
  InferServiceImpl infer_service;

  grpc::EnableDefaultHealthCheckService(true);
  grpc::reflection::InitProtoReflectionServerBuilderPlugin();
  ServerBuilder builder;
  // Listen on the given address without any authentication mechanism.
  builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
  // Register "service" as the instance through which we'll communicate with
  // clients. In this case it corresponds to an *synchronous* service.
  builder.RegisterService(&infer_service);
  // Adjust received message size as transferred messages are large
  int msg_size = 60 * 1024 * 1024;  // 60MB
  builder.SetMaxReceiveMessageSize(msg_size);
  // Finally assemble the server.
  std::unique_ptr<Server> server(builder.BuildAndStart());
  std::cout << "Server listening on " << server_address << std::endl;

  // Wait for the server to shutdown. Note that some other thread must be
  // responsible for shutting down the server for this call to ever return.
  server->Wait();
}

int main(int argc, char** argv) {
  RunServer();
  return 0;
}

