/*
 *
 * Copyright (c) 2022 Intel Corporation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 */

#include <grpcpp/grpcpp.h>
#include <grpcpp/security/sgx/sgx_ra_tls.h>

#ifdef BAZEL_BUILD
#include "examples/protos/psi.grpc.pb.h"
#else
#include "psi.grpc.pb.h"
#endif

#include "getopt.hpp"

#include <string>

using psi::PSI;
using psi::RAReply;
using psi::RARequest;
using psi::ConnectRequest;
using psi::ConnectReply;
using psi::DataUploadRequest;
using psi::UploadReply;
using psi::CalPsiRequest;
using psi::Results;

struct argparser {
    const char* config;
    std::string server_address, client_name, data_dir;
    bool is_chief;
    int client_num;
    
    argparser() {
        server_address = getarg("localhost:70051", "-host", "--host");
        config = getarg("dynamic_config.json", "-cfg", "--config");
	    is_chief = getarg(false, "-is_chief", "--is_chief");
	    client_num = getarg(2, "-client_num", "--client_num");
        data_dir = getarg("data3.txt", "-data_dir", "--data_dir");
        client_name = getarg("data_provider3", "-client_name", "--client_name");

    };
};

class PSIClient {
    public:
        PSIClient(std::shared_ptr<grpc::Channel> channel) : stub_(PSI::NewStub(channel)) {}

        std::string RemoteAttestation(const std::string& client_name) {
            RARequest request;
            request.set_name(client_name);

            RAReply reply;

            grpc::ClientContext context;
            grpc::Status status = stub_->RemoteAttestation(&context, request, &reply);

            if (status.ok()) {
                return reply.message();
            } else {
                std::cout << status.error_code() << ": " << status.error_message() << std::endl;
                return "RPC failed";
            }
        }

        std::string Connect(const std::string& client_name, bool is_chief, int client_num) {
            ConnectRequest request;
            request.set_client_name(client_name);
            request.set_is_chief(is_chief);
            request.set_client_num(client_num);

            ConnectReply reply;

            grpc::ClientContext context;
            grpc::Status status = stub_->Connect(&context, request, &reply);

            if (status.ok()) {
                return reply.message();
            } else {
                std::cout << status.error_code() << ": " << status.error_message() << std::endl;
                return "RPC failed";
            }
        }

        std::string DataUpload(std::vector<std::string> input_data) {
            DataUploadRequest request;
            *request.mutable_input_data() = {input_data.begin(), input_data.end()};
            UploadReply reply;

            grpc::ClientContext context;
            grpc::Status status = stub_->DataUpload(&context, request, &reply);
            
            if (status.ok()) {
                return reply.message();
            } else {
                std::cout << status.error_code() << ": " << status.error_message() << std::endl;
                return "RPC failed";
            }
        }

        std::vector<std::string> CalPsi(std::string client_name, bool is_chief) {
            CalPsiRequest request;
            request.set_client_name(client_name);
            request.set_is_chief(is_chief);
            Results reply;
            std::vector<std::string> results;

            grpc::ClientContext context;
            grpc::Status status = stub_->CalPsi(&context, request, &reply);

            if (status.ok()) {
                for (int i=0; i<(reply.data().size()); i++) {
                    results.push_back((reply.data(i)));
                }
                return results;
            } else {
                std::cout << status.error_code() << ": " << status.error_message() << std::endl;
                std::cout << "RPC failed" << std::endl;
                std::vector<std::string> test1;
                return test1;
            }
        }

    private:
        std::unique_ptr<PSI::Stub> stub_;
};

std::vector <std::string> load_data(std::string data_dir) {
  std::ifstream infile(data_dir);
  std::string line;
  std::vector<std::string> lines;
  while (std::getline(infile, line)) {
      lines.push_back(line);
  }
  return lines;
}

void run_client() {
    argparser args;
    std::string client_name;
    int client_num;
    bool is_chief;

    auto cred = grpc::sgx::TlsCredentials(
                    args.config, GRPC_RA_TLS_TWO_WAY_VERIFICATION);
    auto channel = grpc::CreateChannel(args.server_address, cred);

    PSIClient PSI(channel);

    std::string remote_attestation = PSI.RemoteAttestation(args.client_name);
    std::cout << remote_attestation << std::endl;

    std::string connect = PSI.Connect(client_name=args.client_name, is_chief=args.is_chief, client_num=args.client_num);
    std::cout << connect << std::endl;

    std::vector<std::string> input_data = load_data(args.data_dir);
    std::string dataupload = PSI.DataUpload(input_data=input_data);
    std::cout << dataupload << std::endl;

    std::vector<std::string> calpsi = PSI.CalPsi(client_name=args.client_name, is_chief=args.is_chief);
    for (int i=0; i<(calpsi.size()); i++) {
        std::cout << calpsi[i] << std::endl;
    }
}

int main(int argc, char** argv) {
    run_client();
    return 0;
}
