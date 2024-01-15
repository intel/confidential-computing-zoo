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

#include <grpcpp/security/sgx/sgx_ra_tls_backends.h>
#include <grpcpp/security/sgx/sgx_ra_tls_impl.h>

namespace grpc {
namespace sgx {

void ra_tls_parse_config(ra_tls_config cfg) {
    std::lock_guard<std::mutex> lock(_ctx_.mtx);
    _ctx_.cfg = cfg;
}

void ra_tls_parse_config(const char* file) {
    ra_tls_parse_config(parse_config_json(file));
}

std::vector<std::string> ra_tls_generate_key_cert(int is_dummy) {
    if (is_dummy) {
        return dummy_generate_key_cert();
    } else {
#if defined(SGX_RA_TLS_GRAMINE_BACKEND)
        return gramine_generate_key_cert();
#elif defined(SGX_RA_TLS_OCCLUM_BACKEND)
        return occlum_generate_key_cert();
#elif defined(SGX_RA_TLS_TDX_BACKEND) || defined(SGX_RA_TLS_AZURE_TDX_BACKEND) || defined(SGX_RA_TLS_GCP_TDX_BACKEND)
        return tdx_generate_key_cert();
#elif defined(SGX_RA_TLS_DUMMY_BACKEND)
        return dummy_generate_key_cert();
#endif
    }
}

static std::vector<grpc::experimental::IdentityKeyCertPair> get_identity_key_cert_pairs(
    std::vector<std::string> key_cert) {
    grpc::experimental::IdentityKeyCertPair key_cert_pair;
    key_cert_pair.private_key = key_cert[0];
    key_cert_pair.certificate_chain = key_cert[1];
    std::vector<grpc::experimental::IdentityKeyCertPair> identity_key_cert_pairs;
    identity_key_cert_pairs.emplace_back(key_cert_pair);
    return identity_key_cert_pairs;
}

void credential_option_set_certificate_provider(
    grpc::sgx::CredentialsOptions& options, int is_dummy) {
    std::lock_guard<std::mutex> lock(_ctx_.mtx);

    _ctx_.cache.id++;

    auto certificate_provider = _ctx_.cache.certificate_provider.insert({
            _ctx_.cache.id,
            std::make_shared<grpc::experimental::StaticDataCertificateProvider>(
                get_identity_key_cert_pairs(ra_tls_generate_key_cert(is_dummy)))
        }).first;

    options.set_certificate_provider(certificate_provider->second);
    options.watch_identity_key_cert_pairs();
    options.set_cert_request_type(GRPC_SSL_REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_BUT_DONT_VERIFY);
    options.set_root_cert_name("");
    options.set_identity_cert_name("");
}

void ra_tls_verify_init() {
#if defined(SGX_RA_TLS_GRAMINE_BACKEND)
    gramine_verify_init();
#elif defined(SGX_RA_TLS_OCCLUM_BACKEND)
    occlum_verify_init();
#elif defined(SGX_RA_TLS_TDX_BACKEND) || defined(SGX_RA_TLS_AZURE_TDX_BACKEND) || defined(SGX_RA_TLS_GCP_TDX_BACKEND)
    tdx_verify_init();
#elif defined(SGX_RA_TLS_DUMMY_BACKEND)
    dummy_verify_init();
#endif
}

/*
    certificate verification:
    1. extract SGX quote from "quote" OID extension from crt
    2. compare public key's hash from cert against quote's report_data
    3. prepare user-supplied verification parameter "allow outdated TCB"
    4. call into libsgx_dcap_quoteverify to verify ECDSA/based SGX quote
    5. verify all measurements from the SGX quote
*/
int ra_tls_verify_certificate(const char *der_crt, size_t len) {
#if defined(SGX_RA_TLS_GRAMINE_BACKEND)
    return gramine_verify_cert(der_crt, len);
#elif defined(SGX_RA_TLS_OCCLUM_BACKEND)
    return occlum_verify_cert(der_crt, len);
#elif defined(SGX_RA_TLS_TDX_BACKEND) || defined(SGX_RA_TLS_AZURE_TDX_BACKEND) || defined(SGX_RA_TLS_GCP_TDX_BACKEND)
    return tdx_verify_cert(der_crt, len);
#elif defined(SGX_RA_TLS_DUMMY_BACKEND)
    return dummy_verify_cert(der_crt, len);
#endif
}

ra_tls_measurement ra_tls_parse_measurement(const char *der_crt, size_t len) {
#if defined(SGX_RA_TLS_GRAMINE_BACKEND)
    return gramine_parse_measurement(der_crt, len);
#elif defined(SGX_RA_TLS_OCCLUM_BACKEND)
    return occlum_parse_measurement(der_crt, len);
#elif defined(SGX_RA_TLS_TDX_BACKEND) || defined(SGX_RA_TLS_AZURE_TDX_BACKEND) || defined(SGX_RA_TLS_GCP_TDX_BACKEND)
    return tdx_parse_measurement(der_crt, len);
#elif defined(SGX_RA_TLS_DUMMY_BACKEND)
    return dummy_parse_measurement(der_crt, len);
#endif
}

int TlsAuthorizationCheck::Schedule(grpc::experimental::TlsServerAuthorizationCheckArg* arg) {
    GPR_ASSERT(arg != nullptr);

    char der_crt[CERT_KEY_MAX_SIZE] = "";
    auto peer_cert_buf = arg->peer_cert();
    peer_cert_buf.copy(der_crt, peer_cert_buf.length(), 0);

    int ret = ra_tls_verify_certificate(der_crt, CERT_KEY_MAX_SIZE);
    if (ret != 0) {
        grpc_printf("something went wrong while verifying cert!\n");
        arg->set_success(0);
        arg->set_status(GRPC_STATUS_UNAUTHENTICATED);
    } else {
        arg->set_success(1);
        arg->set_status(GRPC_STATUS_OK);
    }
    return 0;
};

void TlsAuthorizationCheck::Cancel(grpc::experimental::TlsServerAuthorizationCheckArg* arg) {
    GPR_ASSERT(arg != nullptr);
    arg->set_status(GRPC_STATUS_PERMISSION_DENIED);
    arg->set_error_details("cancelled!");
};

int ra_tls_auth_check_schedule(void* /* confiuser_data */,
                               grpc_tls_server_authorization_check_arg* arg) {
    char der_crt[CERT_KEY_MAX_SIZE] = "";
    memcpy(der_crt, arg->peer_cert, strlen(arg->peer_cert));

    int ret = ra_tls_verify_certificate(der_crt, CERT_KEY_MAX_SIZE);
    if (ret != 0) {
        grpc_printf("something went wrong while verifying cert!\n");
        arg->success = 0;
        arg->status = GRPC_STATUS_UNAUTHENTICATED;
    } else {
        arg->success = 1;
        arg->status = GRPC_STATUS_OK;
    }
    return 0;
}

void credential_option_set_authorization_check(grpc::sgx::CredentialsOptions& options) {
    std::lock_guard<std::mutex> lock(_ctx_.mtx);

    _ctx_.cache.id++;

    ra_tls_verify_init();

    auto authorization_check = _ctx_.cache.authorization_check.insert({
            _ctx_.cache.id, std::make_shared<grpc::sgx::TlsAuthorizationCheck>()
        }).first;

    auto authorization_check_config = _ctx_.cache.authorization_check_config.insert({
            _ctx_.cache.id,
            std::make_shared<grpc::experimental::TlsServerAuthorizationCheckConfig>(
                authorization_check->second)
        }).first;

    options.set_authorization_check_config(authorization_check_config->second);
}

} // namespace sgx
} // namespace grpc
