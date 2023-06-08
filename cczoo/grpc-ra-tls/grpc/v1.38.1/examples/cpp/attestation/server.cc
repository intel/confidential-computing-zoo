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
#include <grpcpp/security/sgx/sgx_ra_tls_utils.h>
#include <grpcpp/ext/proto_server_reflection_plugin.h>

#ifdef BAZEL_BUILD
#include "examples/protos/secretmanager.grpc.pb.h"
#else
#include "secretmanager.grpc.pb.h"
#endif

#include <string>
#include <unordered_map>

#include "getopt.hpp"

struct argparser {
    std::string config;
    std::string secret;
    std::string server_address;
    std::string server_key;
    std::string server_cert;
    std::string root_cert;
    argparser() {
        server_address = getarg("localhost:70051", "-host", "--host");
        server_key = getarg("server.key", "-key", "--key");
        server_cert = getarg("server.crt", "-cert", "--cert");
        root_cert = getarg("ca.crt", "-ca", "--root_cert");
        secret = getarg("secret.json", "-s", "--secret");
        config = getarg("dynamic_config.json", "-c", "--config");
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

// Logic and data behind the server's behavior.
class SecretMangerServiceImpl final :
    public Attestation::SecretManger::Service {
public:
    void Init(std::string config_file, std::string secret_file) {
        grpc::sgx::ra_tls_parse_config(config_file.c_str());
        grpc::sgx::ra_tls_verify_init();
        this->ParseSecret(secret_file.c_str());
        return;
    };

    void ParseSecret(const char *secret_file) {
        class grpc::sgx::json_engine secret_json(secret_file);
        auto head = secret_json.get_handle()->child;
        this->secrets.emplace(head->string, head->valuestring);
        while (head) {
            this->secrets.emplace(head->string, head->valuestring);
            head = head->next;
        }
        std::cout << secret_json.print_item(secret_json.get_handle()) << std::endl;
        return;
    };

    grpc::Status GetSecret(grpc::ServerContext* context,
                           const Attestation::SecretRequest* request,
                           Attestation::SecretReply* reply) override {
        auto status = grpc::StatusCode::NOT_FOUND;
        std::string value("");

        auto key = request->key();
        auto ctx = request->ctx();
        // std::cout << key << std::endl;
        // std::cout << ctx << std::endl;

        try {
            if (grpc::sgx::ra_tls_verify_certificate(
                    ctx.c_str(), CERT_KEY_MAX_SIZE)) {
                auto mr = grpc::sgx::ra_tls_parse_measurement(ctx.c_str(), CERT_KEY_MAX_SIZE);
                std::cout << grpc::sgx::byte_to_hex(mr.mr_enclave, 32) << std::endl;
                status = grpc::StatusCode::UNAUTHENTICATED;
            } else {
                value = this->secrets.at(key);
                status = grpc::StatusCode::OK;
            }
            // std::cout << value << std::endl;
            status = grpc::StatusCode::OK;
        } catch (...) {
            std::cout << "Not Found : " << request->key() << std::endl;
        };

        // auto mr = grpc::sgx::ra_tls_parse_measurement(ctx.c_str(), CERT_KEY_MAX_SIZE);
        // std::cout << grpc::sgx::byte_to_hex(mr.mr_enclave, 32) << std::endl;

        fflush(stdout);
        reply->set_value(value);
        return grpc::Status(status, "");
    }
private:
    std::unordered_map<std::string, std::string> secrets;
};

void RunServer() {
    argparser args;

    SecretMangerServiceImpl service;
    service.Init(args.config, args.secret);

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
