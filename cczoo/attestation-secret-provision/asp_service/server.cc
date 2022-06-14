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
#include <grpcpp/ext/proto_server_reflection_plugin.h>

#include <fstream>

#ifdef BAZEL_BUILD
#include "examples/protos/secretmanager.grpc.pb.h"
#else
#include "secretmanager.grpc.pb.h"
#endif

#include "policy_manager.hpp"
#include "kms_agent.hpp"

#include "getopt.hpp"

struct argparser {
    const char* config;
    std::string server_address;
    std::string server_key;
    std::string server_cert;
    std::string root_cert;
    std::string policy_file;
    argparser() {
        server_address = getarg("localhost:70051", "-host", "--host");
        server_key = getarg("server.key", "-key", "--key");
        server_cert = getarg("server.crt", "-cert", "--cert");
        root_cert = getarg("ca.crt", "-ca", "--root_cert");
        policy_file = getarg("policy_vault.json", "-p", "--policy");
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

class SecretMangerServiceImpl final :
    public secretmanager::SecretManger::Service {
public:
    void Init(std::string &policy_file) {
        grpc::sgx::ra_tls_verify_init();
        struct grpc::sgx::ra_tls_config config;
        config.verify_mr_enclave = false;
        config.verify_mr_signer = false;
        config.verify_isv_prod_id = false;
        config.verify_isv_svn = false;
        grpc::sgx::ra_tls_parse_config(config);
        this->policy_manager = std::make_shared<as::PolicyManager>(policy_file);
        return;
    };

    grpc::Status GetSecret(grpc::ServerContext* context,
                           const secretmanager::SecretRequest* request,
                           secretmanager::SecretReply* reply) override {
        auto status = grpc::StatusCode::NOT_FOUND;
        std::string value("");

        try {
            // std::cout << request->key() << std::endl;
            // std::cout << request->ctx() << std::endl;
            auto key = request->key();
            auto ctx = request->ctx();
            if (grpc::sgx::ra_tls_verify_certificate(ctx.c_str(), CERT_KEY_MAX_SIZE)) {
                status = grpc::StatusCode::UNAUTHENTICATED;
            } else {
                auto measurement = grpc::sgx::ra_tls_parse_measurement(ctx.c_str(), CERT_KEY_MAX_SIZE);
                auto mr_enclave = std::string(measurement.mr_enclave);
                auto kms_agent = policy_manager->createKMSAgent(mr_enclave);
                value = kms_agent->getSecret(key);
                status = grpc::StatusCode::OK;
            }
            // std::cout << value << std::endl;
        } catch (...) {
            std::cout << "Not Found : " << request->key() << std::endl;
        };

        reply->set_value(value);
        return grpc::Status(status, "");
    }
private:
    std::shared_ptr<as::PolicyManager> policy_manager;
};

void RunServer() {
    argparser args;

    SecretMangerServiceImpl service;
    service.Init(args.policy_file);

    grpc::EnableDefaultHealthCheckService(true);
    grpc::reflection::InitProtoReflectionServerBuilderPlugin();

    grpc::ServerBuilder builder;

    grpc::SslServerCredentialsOptions options;
    grpc::SslServerCredentialsOptions::PemKeyCertPair pkcp;
    pkcp.private_key = read_file(args.server_key);
    pkcp.cert_chain  = read_file(args.server_cert);
    options.pem_key_cert_pairs.push_back(pkcp);
    options.pem_root_certs = read_file(args.root_cert);

    auto creds = grpc::SslServerCredentials(options);
    GPR_ASSERT(creds.get() != nullptr);

    builder.AddListeningPort(args.server_address, creds);
    builder.RegisterService(&service);

    std::unique_ptr<grpc::Server> server(builder.BuildAndStart());
    std::cout << "Server listening on " << args.server_address << std::endl;

    server->Wait();
}

int main(int argc, char** argv) {
    RunServer();
    return 0;
}
