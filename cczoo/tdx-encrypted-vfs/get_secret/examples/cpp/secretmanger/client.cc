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
#include "examples/protos/secretmanger.grpc.pb.h"
#else
#include "secretmanger.grpc.pb.h"
#endif

#include "getopt.hpp"


struct argparser {
    const char* config;
    std::string key;
    std::string server_address;
    argparser() {
        server_address = getarg("localhost:50051", "-host", "--host");
        config = getarg("dynamic_config.json", "-cfg", "--config");
        key = getarg("", "-key", "--key");
    };
};

class SecretClient {
    public:
        SecretClient(std::shared_ptr<grpc::Channel> channel) : stub_(secretmanger::SecretManger::NewStub(channel)) {}

        std::string GetSecret(const std::string& key) {
            grpc::ClientContext context;
            secretmanger::SecretReply reply;
            secretmanger::SecretRequest request;
            request.set_name(key);

            grpc::Status status = stub_->GetSecret(&context, request, &reply);

            if (status.ok()) {
                return reply.message();
            } else {
                std::cout << status.error_code() << ": " << status.error_message() << std::endl;
                return "RPC failed";
            }
        }

    private:
        std::unique_ptr<secretmanger::SecretManger::Stub> stub_;
};

void run_client() {
    argparser args;

    auto cred = grpc::sgx::TlsCredentials(
                    args.config, GRPC_RA_TLS_CLIENT_VERIFICATION);
    auto channel = grpc::CreateChannel(args.server_address, cred);

    SecretClient client(channel);

    std::string value = client.GetSecret(args.key);

    std::cout << "Secret received: " << value << std::endl;
};

int main(int argc, char** argv) {
    run_client();
    return 0;
}
