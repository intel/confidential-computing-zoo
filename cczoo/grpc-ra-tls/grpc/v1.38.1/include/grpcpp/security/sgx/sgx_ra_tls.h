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

#ifndef SGX_RA_TLS_H
#define SGX_RA_TLS_H

#include <memory>

#include <grpcpp/security/sgx/sgx_ra_tls_backends.h>
#include <grpcpp/security/sgx/sgx_ra_tls_context.h>

#define CERT_KEY_MAX_SIZE 16000

namespace grpc {
namespace sgx {

std::vector<std::string> ra_tls_generate_key_cert(int is_dummy);

void ra_tls_parse_config(ra_tls_config cfg);

void ra_tls_parse_config(const char *file);

void ra_tls_verify_init();

int ra_tls_verify_certificate(const char *der_crt, size_t len);

ra_tls_measurement ra_tls_parse_measurement(const char *der_crt, size_t len);

int ra_tls_auth_check_schedule(void * /* config_user_data */,
                               grpc_tls_server_authorization_check_arg *arg);

std::shared_ptr<grpc::ChannelCredentials> TlsCredentials(
    ra_tls_config cfg, grpc_tls_server_verification_option verify_option=GRPC_RA_TLS_TWO_WAY_VERIFICATION);

std::shared_ptr<grpc::ChannelCredentials> TlsCredentials(
    const char* cfg_json, grpc_tls_server_verification_option verify_option=GRPC_RA_TLS_TWO_WAY_VERIFICATION);

std::shared_ptr<grpc::ServerCredentials> TlsServerCredentials(
    ra_tls_config cfg, grpc_tls_server_verification_option verify_option=GRPC_RA_TLS_TWO_WAY_VERIFICATION);

std::shared_ptr<grpc::ServerCredentials> TlsServerCredentials(
    const char* cfg_json, grpc_tls_server_verification_option verify_option=GRPC_RA_TLS_TWO_WAY_VERIFICATION);

std::shared_ptr<grpc::Channel> CreateSecureChannel(
    string target_str, std::shared_ptr<grpc::ChannelCredentials> channel_creds);

}  // namespace sgx
}  // namespace grpc

#endif  // SGX_RA_TLS_H
