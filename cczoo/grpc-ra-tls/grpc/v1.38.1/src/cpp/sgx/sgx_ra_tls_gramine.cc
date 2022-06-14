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

#ifdef SGX_RA_TLS_GRAMINE_BACKEND

#include "sgx_ra_tls_impl.h"

namespace grpc {
namespace sgx {

#include <mbedtls/config.h>
#include <mbedtls/certs.h>
#include <mbedtls/ctr_drbg.h>
#include <mbedtls/debug.h>
#include <mbedtls/entropy.h>
#include <mbedtls/error.h>
#include <mbedtls/net_sockets.h>
#include <mbedtls/ssl.h>
#include <mbedtls/x509.h>
#include <mbedtls/x509_crt.h>
#include <mbedtls/pk.h>
#include <mbedtls/pem.h>
#include <mbedtls/base64.h>
#include <mbedtls/ecdsa.h>
#include <mbedtls/rsa.h>

std::vector<std::string> gramine_generate_key_cert() {
    if (!_ctx_.attest_lib.get_handle()) {
        _ctx_.attest_lib.open("libra_tls_attest.so", RTLD_LAZY);
    }

    auto ra_tls_create_key_and_crt =
        reinterpret_cast<int (*)(mbedtls_pk_context*, mbedtls_x509_crt*)>(
            _ctx_.attest_lib.get_func("ra_tls_create_key_and_crt"));

    std::string error = "";
    std::vector<std::string> key_cert;

    mbedtls_x509_crt srvcert;
    mbedtls_pk_context pkey;

    mbedtls_x509_crt_init(&srvcert);
    mbedtls_pk_init(&pkey);

    int ret = (*ra_tls_create_key_and_crt)(&pkey, &srvcert);
    if (ret != 0) {
        error = "gramine_generate_key_cert->ra_tls_create_key_and_crt";
        goto out;
    }

    unsigned char private_key_pem[CERT_KEY_MAX_SIZE],
                  cert_pem[CERT_KEY_MAX_SIZE];
    size_t olen;

    ret = mbedtls_pk_write_key_pem(&pkey, private_key_pem, CERT_KEY_MAX_SIZE);
    if (ret != 0) {
        error = "gramine_generate_key_cert->mbedtls_pk_write_key_pem";
        goto out;
    }

    ret = mbedtls_pem_write_buffer("-----BEGIN CERTIFICATE-----\n",
                                   "-----END CERTIFICATE-----\n",
                                   srvcert.raw.p, srvcert.raw.len,
                                   cert_pem, CERT_KEY_MAX_SIZE, &olen);
    if (ret != 0) {
        error = "gramine_generate_key_cert->mbedtls_pem_write_buffer";
        goto out;
    };

    key_cert.emplace_back(std::string((char*) private_key_pem));
    key_cert.emplace_back(std::string((char*) cert_pem));

out:
    mbedtls_x509_crt_free(&srvcert);
    mbedtls_pk_free(&pkey);

    if (ret != 0) {
        throw std::runtime_error(
            std::string((error + std::string(" failed: %s\n")).c_str(),
                        mbedtls_high_level_strerr(ret)));
    }

    return key_cert;
};

void gramine_verify_init() {
    if (!_ctx_.verify_lib.get_handle()) {
        _ctx_.verify_lib.open("libra_tls_verify_dcap_gramine.so", RTLD_LAZY);
    }

    if (!_ctx_.verify_callback_f) {
        _ctx_.verify_callback_f =
            reinterpret_cast<int (*)(uint8_t* der_crt, size_t len)>(
                _ctx_.verify_lib.get_func("ra_tls_verify_callback_der"));
    }

    auto set_verify_mr_callback =
        reinterpret_cast<void (*)(int (*)(const char *mr_enclave,
                                          const char *mr_signer,
                                          const char *isv_prod_id,
                                          const char *isv_svn))>(
            _ctx_.verify_lib.get_func("ra_tls_set_measurement_callback"));
    (*set_verify_mr_callback)(verify_measurement);
}

int gramine_verify_cert(const char *der_crt, size_t len) {
    return (*_ctx_.verify_callback_f)((uint8_t*)((void*)der_crt), len);
}

ra_tls_measurement gramine_parse_measurement(const char *der_crt, size_t len) {
    // TODO
    return ra_tls_measurement();
}

} // namespace sgx
} // namespace grpc

#endif // SGX_RA_TLS_GRAMINE_BACKEND
