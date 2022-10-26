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

#ifndef INFER_CLIENT_HPP_
#define INFER_CLIENT_HPP_

#include <grpcpp/grpcpp.h>
#include <gsl/span>
#include "param.hpp"
#include "seal/seal.h"
#include "inference.grpc.pb.h"
#include "infer_base.hpp"

using grpc::ClientContext;
using grpc::Status;
using grpc::Channel;
using inference::InitCtxRequest;
using inference::InitCtxReply;
using inference::InferRequest;
using inference::InferReply;

class InferClient : public InferBase {
public:
  InferClient(HEParam& param, std::shared_ptr<grpc::Channel> channel);
  void initContext(HEParam& param);
  void loadDataSet(std::string& file_name);
  void encodeEncryptData();
  bool initServerCtx();
  std::vector<seal::Ciphertext> infer();
  std::vector<double> decryptDecodeResult(
    std::vector<seal::Ciphertext>& encrypted_result);
  std::vector<double> getEvalTarget() {
    return eval_target_;
  }

private:
  seal::Plaintext encode(const gsl::span<const double>& v);
  seal::Ciphertext encrypt(const seal::Plaintext& v);

  seal::EncryptionParameters enc_params_;
  std::shared_ptr<seal::SEALContext> context_;
  seal::PublicKey public_key_;
  seal::SecretKey secret_key_;
  seal::RelinKeys relin_keys_;
  // seal::GaloisKeys galois_keys_;
  std::shared_ptr<seal::Encryptor> encryptor_;
  std::shared_ptr<seal::Decryptor> decryptor_;
  std::shared_ptr<seal::CKKSEncoder> encoder_;
  size_t slot_count_;
  seal::sec_level_type sec_level_;
  double scale_;
  std::vector<std::vector<double>> eval_data_;
  std::vector<double> eval_target_;
  std::vector<std::vector<seal::Ciphertext>> encrypted_data_;
  std::unique_ptr<inference::Inference::Stub> stub_;
};
#endif // INFER_CLIENT_HPP_
