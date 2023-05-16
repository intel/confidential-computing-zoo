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
#include "examples/protos/secretmanager.grpc.pb.h"
#else
#include "secretmanager.grpc.pb.h"
#endif

#include "getopt.hpp"

struct argparser {
    std::string server_address;
    std::string root_cert;
    std::string key;
    argparser() {
        server_address = getarg("localhost:70051", "-host", "--host");
        root_cert = getarg("ca.crt", "-ca", "--root_cert");
        key = getarg("", "-key", "--key");
    };
};

std::string read_file(const char *file_path) {
    std::ifstream in(file_path, std::ios::in);
    std::ostringstream out;
    out << in.rdbuf();
    return std::string(out.str());
}

std::string read_file(std::string file_path) {
    return read_file(file_path.c_str());
}

class SecretClient {
    public:
        SecretClient(std::shared_ptr<grpc::Channel> channel) : stub_(Attestation::SecretManger::NewStub(channel)) {}

        std::string GetSecret(const std::string& key) {
            grpc::ClientContext context;
            Attestation::SecretReply reply;
            Attestation::SecretRequest request;

            auto cert = grpc::sgx::ra_tls_generate_key_cert(0)[1];

            request.set_key(key);
            request.set_ctx(cert);

            grpc::Status status = stub_->GetSecret(&context, request, &reply);

            if (status.ok()) {
                return reply.value();
            } else {
                std::cout << "Error code: " << status.error_code() << ", message: " << status.error_message() << std::endl;
                return "RPC failed";
            }
        }

    private:
        std::unique_ptr<Attestation::SecretManger::Stub> stub_;
};

void run_client() {
    argparser args;

    grpc::SslCredentialsOptions options;
    options.pem_root_certs  = read_file(args.root_cert);
    options.pem_cert_chain  = "";
    options.pem_private_key = "";

    auto creds = grpc::SslCredentials(options);
    auto channel = grpc::CreateChannel(args.server_address, creds);

    SecretClient client(channel);

    std::string value = client.GetSecret(args.key);
    std::cout << "Secret received: " << value << std::endl;
};

int main(int argc, char** argv) {
    run_client();
    return 0;
}
