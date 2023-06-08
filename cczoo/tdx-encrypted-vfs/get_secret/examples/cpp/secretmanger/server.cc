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
#include "examples/protos/secretmanger.grpc.pb.h"
#else
#include "secretmanger.grpc.pb.h"
#endif

#include <string>
#include <unordered_map>

#include "getopt.hpp"

struct argparser {
    const char* config;
    const char* secret;
    std::string server_address;
    argparser() {
        server_address = getarg("localhost:50051", "-host", "--host");
        config = getarg("dynamic_config.json", "-cfg", "--config");
        secret = getarg("secret.json", "-s", "--secret");
    };
};

// Logic and data behind the server's behavior.
class SecretMangerServiceImpl final :
    public secretmanger::SecretManger::Service {
public:
    void ParseSecret(const char * secret_file) {
        class grpc::sgx::json_engine secret_json(secret_file);

        auto head = secret_json.get_handle()->child;
        this->secrets.emplace(head->string, head->valuestring);

        while (head) {
            this->secrets.emplace(head->string, head->valuestring);
            head = head->next;
        }

        printf("%s", secret_json.print_item(secret_json.get_handle()));
        return;
    };

    grpc::Status GetSecret(grpc::ServerContext* context,
                           const secretmanger::SecretRequest* request,
                           secretmanger::SecretReply* reply) override {
        auto status = grpc::StatusCode::NOT_FOUND;
        std::string value("");

        try {
            // std::cout << request->name() << std::endl;
            value = this->secrets.at(request->name());
            // std::cout << value << std::endl;
            status = grpc::StatusCode::OK;
        } catch (...) {
            std::cout << "Not Found : " << request->name() << std::endl;
        };

        reply->set_message(value);
        return grpc::Status(status, "");
    }
private:
    std::unordered_map<std::string, std::string> secrets;
};

void RunServer() {
    argparser args;

    SecretMangerServiceImpl service;
    service.ParseSecret(args.secret);

    grpc::EnableDefaultHealthCheckService(true);
    grpc::reflection::InitProtoReflectionServerBuilderPlugin();

    grpc::ServerBuilder builder;

    auto creds = grpc::sgx::TlsServerCredentials(
                    args.config, GRPC_RA_TLS_CLIENT_VERIFICATION);
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
