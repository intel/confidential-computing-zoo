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

#include <grpcpp/security/sgx/sgx_ra_tls_backends.h>
#include <grpcpp/security/sgx/sgx_ra_tls_impl.h>

namespace grpc {
namespace sgx {

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
    std::vector<std::string> key_cert;
    unsigned char key_buffer[CERT_KEY_MAX_SIZE],
                  cert_buffer[CERT_KEY_MAX_SIZE];
    uint8_t *der_key = nullptr, *der_crt = nullptr;
    size_t der_key_size, der_crt_size, olen;
    std::string error = "";

    mbedtls_x509_crt cert;
    mbedtls_pk_context key;
    mbedtls_ctr_drbg_context ctr_drbg;

    mbedtls_x509_crt_init(&cert);
    mbedtls_pk_init(&key);
    mbedtls_ctr_drbg_init(&ctr_drbg);

    if (!_ctx_.attest_lib.get_handle()) {
        _ctx_.attest_lib.open("libra_tls_attest.so", RTLD_LAZY);
    }

    auto ra_tls_create_key_and_crt_der_f =
        reinterpret_cast<int (*)(uint8_t**, size_t*, uint8_t**, size_t*)>(
            _ctx_.attest_lib.get_func("ra_tls_create_key_and_crt_der"));

    int ret = (*ra_tls_create_key_and_crt_der_f)(&der_key, &der_key_size, &der_crt, &der_crt_size);
    if (ret != 0) {
        error = "ra_tls_get_key_cert->ra_tls_create_key_and_crt_der_f";
        goto out;
    }

    ret = mbedtls_x509_crt_parse(&cert, (unsigned char*)der_crt, der_crt_size);
    if (ret != 0) {
        error = "ra_tls_get_key_cert->mbedtls_x509_crt_parse";
        goto out;
    }

    ret = mbedtls_pk_parse_key(&key, (unsigned char*)der_key, der_key_size, /*pwd=*/NULL, 0,
                                mbedtls_ctr_drbg_random, &ctr_drbg);
    if (ret != 0) {
        error = "ra_tls_get_key_cert->mbedtls_pk_parse_key";
        goto out;
    }

    ret = mbedtls_pk_write_key_pem(&key, key_buffer, CERT_KEY_MAX_SIZE);
    if (ret != 0) {
        error = "gramine_generate_key_cert->mbedtls_pk_write_key_pem";
        goto out;
    }

    ret = mbedtls_pem_write_buffer("-----BEGIN CERTIFICATE-----\n",
                                   "-----END CERTIFICATE-----\n",
                                   cert.raw.p, cert.raw.len,
                                   cert_buffer, CERT_KEY_MAX_SIZE, &olen);
    if (ret != 0) {
        error = "gramine_generate_key_cert->mbedtls_pem_write_buffer";
        goto out;
    };

    key_cert.emplace_back(std::string((char*) key_buffer));
    key_cert.emplace_back(std::string((char*) cert_buffer));

out:
    mbedtls_pk_free(&key);
    mbedtls_x509_crt_free(&cert);
    mbedtls_ctr_drbg_free(&ctr_drbg);
    check_free(der_key);
    check_free(der_crt);

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
    return (*_ctx_.verify_callback_f)((uint8_t*)der_crt, len);
}

int gramine_parse_mr_callback(const char* mr_enclave, const char* mr_signer,
                              const char* isv_prod_id, const char* isv_svn) {
    struct ra_tls_measurement mr;
    memcpy(mr.mr_enclave, mr_enclave, 32);
    memcpy(mr.mr_signer, mr_signer, 32);
    mr.isv_prod_id = *(uint16_t*)isv_prod_id;
    mr.isv_svn = *(uint16_t*)isv_svn;
    _ctx_.cache.mrs.insert({0, mr});
    return 0;
}

ra_tls_measurement gramine_parse_measurement(const char *crt, size_t len) {
    std::lock_guard<std::mutex> lock(_ctx_.mtx);

    auto set_verify_mr_callback =
        reinterpret_cast<void (*)(int (*)(const char *mr_enclave,
                                          const char *mr_signer,
                                          const char *isv_prod_id,
                                          const char *isv_svn))>(
            _ctx_.verify_lib.get_func("ra_tls_set_measurement_callback"));
    (*set_verify_mr_callback)(gramine_parse_mr_callback);

    gramine_verify_cert(crt, len);
    ra_tls_measurement mr = _ctx_.cache.mrs[0];

    set_verify_mr_callback =
        reinterpret_cast<void (*)(int (*)(const char *mr_enclave,
                                          const char *mr_signer,
                                          const char *isv_prod_id,
                                          const char *isv_svn))>(
            _ctx_.verify_lib.get_func("ra_tls_set_measurement_callback"));
    (*set_verify_mr_callback)(verify_measurement);

    return mr;
}

} // namespace sgx
} // namespace grpc

#endif // SGX_RA_TLS_GRAMINE_BACKEND
