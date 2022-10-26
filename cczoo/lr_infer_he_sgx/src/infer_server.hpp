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

#ifndef INFER_SERVER_HPP_
#define INFER_SERVER_HPP_

#include <grpcpp/grpcpp.h>
#include <grpcpp/health_check_service_interface.h>
#include <grpcpp/ext/proto_server_reflection_plugin.h>

#include "inference.grpc.pb.h"
#include "seal/seal.h"
#include "infer_base.hpp"

using grpc::Server;
using grpc::ServerBuilder;
using grpc::ServerContext;
using grpc::Status;
using inference::InitCtxRequest;
using inference::InitCtxReply;
using inference::InferRequest;
using inference::InferReply;
using inference::Inference;

const double sigmoid_coeff_3[] = {0.5, 0.15012, 0.0, -0.001593008};

class InferServer : public InferBase {
public:
void initContext(std::stringstream& params_stream,
  std::stringstream& pubkey_stream,
  std::stringstream& relinkey_stream,
  int security_level, double scale);
void loadWeights(std::string& model_file);
std::vector<seal::Ciphertext> inference(
  std::stringstream& input, int batches, int batch_size);
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
  double scale_;
};

class InferServiceImpl final : public Inference::Service {
public:
  Status InitCtx(ServerContext* context, const InitCtxRequest* request,
                 InitCtxReply* reply) override;
  Status Infer(ServerContext* context, const InferRequest* request,
               InferReply* reply) override;
private:
  InferServer server_;
};
#endif // INFER_SERVER_HPP_
