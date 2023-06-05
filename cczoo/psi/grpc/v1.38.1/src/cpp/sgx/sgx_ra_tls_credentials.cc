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

#include "sgx_ra_tls_backends.h"

namespace grpc {
namespace sgx {

std::shared_ptr<grpc::ChannelCredentials> TlsCredentials(
    ra_tls_config cfg, grpc_tls_server_verification_option verify_option=GRPC_RA_TLS_TWO_WAY_VERIFICATION) {
    ra_tls_parse_config(cfg);

    grpc::sgx::CredentialsOptions options(verify_option);
    int is_dummy = verify_option == GRPC_RA_TLS_SERVER_VERIFICATION;
    credential_option_set_certificate_provider(options, is_dummy);
    credential_option_set_authorization_check(options);

    return grpc::experimental::TlsCredentials(
        reinterpret_cast<const grpc::experimental::TlsChannelCredentialsOptions&>(options));
};

std::shared_ptr<grpc::ChannelCredentials> TlsCredentials(
    const char* cfg_json, grpc_tls_server_verification_option verify_option=GRPC_RA_TLS_TWO_WAY_VERIFICATION) {
    ra_tls_parse_config(cfg_json);

    grpc::sgx::CredentialsOptions options(verify_option);
    int is_dummy = verify_option == GRPC_RA_TLS_SERVER_VERIFICATION;
    credential_option_set_certificate_provider(options, is_dummy);
    credential_option_set_authorization_check(options);

    return grpc::experimental::TlsCredentials(
        reinterpret_cast<const grpc::experimental::TlsChannelCredentialsOptions&>(options));
};

std::shared_ptr<grpc::ServerCredentials> TlsServerCredentials(
    ra_tls_config cfg, grpc_tls_server_verification_option verify_option=GRPC_RA_TLS_TWO_WAY_VERIFICATION) {
    ra_tls_parse_config(cfg);

    grpc::sgx::CredentialsOptions options(verify_option);
    int is_dummy = verify_option == GRPC_RA_TLS_CLIENT_VERIFICATION;
    credential_option_set_certificate_provider(options, is_dummy);
    credential_option_set_authorization_check(options);

    return grpc::experimental::TlsServerCredentials(
        reinterpret_cast<const grpc::experimental::TlsServerCredentialsOptions&>(options));
};

std::shared_ptr<grpc::ServerCredentials> TlsServerCredentials(
    const char* cfg_json, grpc_tls_server_verification_option verify_option=GRPC_RA_TLS_TWO_WAY_VERIFICATION) {
    ra_tls_parse_config(cfg_json);

    grpc::sgx::CredentialsOptions options(verify_option);
    int is_dummy = verify_option == GRPC_RA_TLS_CLIENT_VERIFICATION;
    credential_option_set_certificate_provider(options, is_dummy);
    credential_option_set_authorization_check(options);

    return grpc::experimental::TlsServerCredentials(
        reinterpret_cast<const grpc::experimental::TlsServerCredentialsOptions&>(options));
};

std::shared_ptr<grpc::Channel> CreateSecureChannel(
    string target_str, std::shared_ptr<grpc::ChannelCredentials> channel_creds) {
    GPR_ASSERT(channel_creds.get() != nullptr);
    auto channel_args = grpc::ChannelArguments();
    channel_args.SetSslTargetNameOverride("RATLS");
    return grpc::CreateCustomChannel(target_str, std::move(channel_creds), channel_args);
};

} // namespace sgx
} // namespace grpc
