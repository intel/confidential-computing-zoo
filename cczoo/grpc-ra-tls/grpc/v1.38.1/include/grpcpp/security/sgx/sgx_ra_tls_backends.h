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

#ifndef SGX_RA_TLS_BACKENDS_H
#define SGX_RA_TLS_BACKENDS_H

#include <grpcpp/security/credentials.h>
#include <grpcpp/security/server_credentials.h>
#include <grpcpp/security/sgx/sgx_ra_tls_options.h>
#include <grpcpp/security/sgx/sgx_ra_tls_context.h>

// Set 1 for strict security checks
#define SGX_MESUREMENTS_MAX_SIZE 16

namespace grpc {
namespace sgx {

class TlsAuthorizationCheck
    : public grpc::experimental::TlsServerAuthorizationCheckInterface {
    int Schedule(grpc::experimental::TlsServerAuthorizationCheckArg* arg) override;
    void Cancel(grpc::experimental::TlsServerAuthorizationCheckArg* arg) override;
};

int dummy_generate_quote(uint8_t **quote_buf, uint32_t &quote_size, uint8_t *hash);

std::vector<std::string> dummy_generate_key_cert();

void dummy_verify_init();

int dummy_verify_cert(const char *der_crt, size_t len);

ra_tls_measurement dummy_parse_measurement(const char *der_crt, size_t len);

#if defined(SGX_RA_TLS_GRAMINE_BACKEND)

std::vector<std::string> gramine_generate_key_cert();

void gramine_verify_init();

int gramine_verify_cert(const char *der_crt, size_t len);

ra_tls_measurement gramine_parse_measurement(const char *der_crt, size_t len);

#elif defined(SGX_RA_TLS_OCCLUM_BACKEND)

std::vector<std::string> occlum_generate_key_cert();

void occlum_verify_init();

int occlum_verify_cert(const char *der_crt, size_t len);

ra_tls_measurement occlum_parse_measurement(const char *der_crt, size_t len);

#elif defined(SGX_RA_TLS_TDX_BACKEND) || defined(SGX_RA_TLS_AZURE_TDX_BACKEND)

std::vector<std::string> tdx_generate_key_cert();

void tdx_verify_init();

int tdx_verify_cert(const char *der_crt, size_t len);

ra_tls_measurement tdx_parse_measurement(const char *der_crt, size_t len);

#endif

std::vector<std::string> ra_tls_generate_key_cert(int is_dummy);

void ra_tls_parse_config(ra_tls_config cfg);

void ra_tls_parse_config(const char *file);

void ra_tls_verify_init();

int ra_tls_verify_certificate(const char *der_crt, size_t len);

ra_tls_measurement ra_tls_parse_measurement(const char *der_crt, size_t len);

void credential_option_set_certificate_provider(grpc::sgx::CredentialsOptions& options, int is_dummy);

void credential_option_set_authorization_check(grpc::sgx::CredentialsOptions& options);


} // namespace sgx
} // namespace grpc

#endif // SGX_RA_TLS_BACKENDS_H
