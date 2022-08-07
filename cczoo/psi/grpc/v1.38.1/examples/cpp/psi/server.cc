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

#ifdef BAZEL_BUILD
#include "examples/protos/psi.grpc.pb.h"
#else
#include "psi.grpc.pb.h"
#endif

#include "getopt.hpp"

#include <string>
#include <vector>
#include <map>

using psi::PSI;
using psi::RAReply;
using psi::RARequest;
using psi::ConnectRequest;
using psi::ConnectReply;
using psi::DataUploadRequest;
using psi::DataUploadRequest;
using psi::UploadReply;
using psi::CalPsiRequest;
using psi::Results;

struct argparser {
    const char* config;
    std::string server_address;
    argparser() {
        server_address = getarg("localhost:70051", "-host", "--host");
        config = getarg("dynamic_config.json", "-cfg", "--config");
    };
};

std::vector<std::string> cal_psi(std::vector<std::vector<std::string>> data, int cur_client_num) {
    std::vector<std::string> intersection;
    if (cur_client_num == 2) {
        std::vector<std::string> data1 = data[0];
        std::vector<std::string> data2 = data[1];
        sort(data1.begin(), data1.end());
        sort(data2.begin(), data2.end());
        int length1 = data1.size(), length2 = data2.size();
        int index1 = 0, index2 = 0;
        while (index1 < length1 && index2 < length2) {
            std::string data_1 = data1[index1], data_2 = data2[index2];
            if (data_1 == data_2) {
                if (!intersection.size() || data_1 != intersection.back()) {
                    intersection.push_back(data_1);
                }
                index1++;
                index2++;
            } else if (data_1 < data_2) {
                index1++;
            } else {
                index2++;
            }
        }
        std::cout << intersection.size() << std::endl;
        return intersection;
    }
    else if (cur_client_num >= 3) {
        std::vector<std::string> data_tmp;
        for (int i=0; i<data.size(); i++) {
            // data_tmp.push_back(data[i]);
            data_tmp.insert(data_tmp.end(), data[i].begin(), data[i].end());
        }
        std::map<std::string, int> count;
        for (int i=0; i<data_tmp.size(); i++) {
            count[data_tmp[i]]++;
        }
        for (auto item=count.begin(); item != count.end(); item++) {
            if (item->second == cur_client_num) {
                intersection.push_back(item->first);
            }
        }
        return intersection;
    }
    else {
        std::cout << "Please make sure at least 2 clients!" << std::endl;
        return intersection;
    }
}


class PSIServiceImpl final : public PSI::Service {
    public:
        grpc::Status RemoteAttestation(
            grpc::ServerContext* context, const RARequest* request, RAReply* reply) override {
            reply->set_message("Remote attestation succeed!");
            std::cout << request->name() << ": Remote attestation succeed!" << std::endl;
            return grpc::Status::OK;
        }

        grpc::Status Connect(
            grpc::ServerContext* context, const ConnectRequest* request, ConnectReply* reply) override {
            cur_client_num += 1;
            if (request->is_chief()) {
                chief = request->client_name();
            }
            std::cout <<"Current client number: " << cur_client_num << std::endl;
            std::cout << "Connect " << request->client_name() << " successfully." << std::endl;
            while (true) {
                if (request->client_num() == cur_client_num) {
                    reply->set_message("All clients connect successfully.");
                    return grpc::Status::OK;
                }
            }
        }

        grpc::Status DataUpload(
            grpc::ServerContext* context, const DataUploadRequest* request, UploadReply* reply) override {
            std::vector<std::string> tmp_data;
            for (int i=0; i<(request->input_data().size()); i++) {
                tmp_data.push_back((request->input_data(i)));
            }
            // tmp_data = request->mutable_input_data();
            data.push_back(tmp_data);
            cur_data += 1;
            while (true) {
                if (cur_data == cur_client_num) {
                    break;
                }
            }
            reply->set_message("All data uploaded");
            return grpc::Status::OK;
        }

        grpc::Status CalPsi(
            grpc::ServerContext* context, const CalPsiRequest* request, Results* reply) override {
            if (request->client_name() != "" && request->client_name() == chief) {
                res = cal_psi(data, cur_client_num);
            }
            while (true) {
                if (!res.empty()) {
                    *reply->mutable_data() = {res.begin(), res.end()};
                    std::cout << "Return calculation results to clients." << std::endl;
                    return grpc::Status::OK;
                }
            }
        }

    private:
        int cur_client_num = 0;
        int cur_data = 0;
        std::string chief;
        std::vector<std::vector<std::string>> data;
        std::vector<std::string> res;
};

void RunServer() {
    argparser args;

    PSIServiceImpl service;

    grpc::EnableDefaultHealthCheckService(true);
    grpc::reflection::InitProtoReflectionServerBuilderPlugin();

    grpc::ServerBuilder builder;

    auto creds = grpc::sgx::TlsServerCredentials(
                    args.config, GRPC_RA_TLS_TWO_WAY_VERIFICATION);
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
