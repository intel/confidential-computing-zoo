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

#ifndef SGX_RA_TLS_CONTEXT_H
#define SGX_RA_TLS_CONTEXT_H

#include "sgx_ra_tls_utils.h"

#include <mutex>
#include <unordered_map>

#include <grpcpp/grpcpp.h>
#include <grpc/grpc_security.h>
#include <grpc/grpc_security_constants.h>
#include <grpcpp/security/credentials.h>
#include <grpcpp/security/tls_certificate_provider.h>

#define CERT_KEY_MAX_SIZE 16000

namespace grpc {
namespace sgx {

class TlsAuthorizationCheck;

struct ra_tls_measurement {
    char mr_enclave[32];
    char mr_signer[32];
    uint16_t isv_prod_id;
    uint16_t isv_svn;
};

struct ra_tls_config {
    bool verify_mr_enclave  = true;
    bool verify_mr_signer   = true;
    bool verify_isv_prod_id = true;
    bool verify_isv_svn     = true;
    std::vector<ra_tls_measurement> mrs;
};

struct ra_tls_cache {
    int id = 0;
    std::unordered_map<
            int, std::shared_ptr<grpc::experimental::StaticDataCertificateProvider>
        > certificate_provider;
    std::unordered_map<
            int, std::shared_ptr<grpc::sgx::TlsAuthorizationCheck>
        > authorization_check;
    std::unordered_map<
            int, std::shared_ptr<grpc::experimental::TlsServerAuthorizationCheckConfig>
        > authorization_check_config;
};

struct ra_tls_context {
    std::mutex mtx;
    struct ra_tls_config cfg;
    struct ra_tls_cache cache;
#ifdef SGX_RA_TLS_GRAMINE_BACKEND
    class library_engine attest_lib;
    class library_engine verify_lib;
    class library_engine sgx_urts_lib;
    int (*verify_callback_f)(uint8_t* der_crt, size_t der_crt_size) = nullptr;
#endif
#ifdef SGX_RA_TLS_LIBRATS_SDK
    class library_engine attest_lib;
    class library_engine verify_lib;
    class library_engine init_lib;
    class library_engine cleanup_lib;
#endif
};

extern struct ra_tls_context _ctx_;

} // namespace sgx
} // namespace grpc

#endif // SGX_RA_TLS_CONTEXT_H
