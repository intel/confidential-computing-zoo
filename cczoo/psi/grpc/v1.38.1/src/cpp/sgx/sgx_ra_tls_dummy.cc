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

// #ifdef SGX_RA_TLS_DUMMY_BACKEND

#include "sgx_ra_tls_impl.h"
#include "sgx_ra_tls_backends.h"

namespace grpc {
namespace sgx {

int dummy_generate_quote(
        uint8_t **quote_buf, uint32_t &quote_size, uint8_t *hash) {
    quote_size = 0;
    *quote_buf = (uint8_t*)calloc(quote_size+SHA256_DIGEST_LENGTH, sizeof(char));
    memcpy((*quote_buf)+quote_size, hash, SHA256_DIGEST_LENGTH);
    quote_size += SHA256_DIGEST_LENGTH;
    return 1;
};

std::vector<std::string> dummy_generate_key_cert() {
    return generate_key_cert(dummy_generate_quote);
};

void dummy_verify_init() {
    struct ra_tls_config config;
    config.verify_mr_enclave = false;
    config.verify_mr_signer = false;
    config.verify_isv_prod_id = false;
    config.verify_isv_svn = false;
    ra_tls_parse_config(config);
};

int dummy_parse_quote(X509 *x509, uint8_t **quote, uint32_t &quote_size) {
    return parse_quote(x509, quote, quote_size);
};

int dummy_verify_quote(uint8_t *quote_buf, size_t quote_size) {
    return 0;
}

int dummy_verify_cert(const char *der_crt, size_t crt_size) {
    int ret = 0;
    uint32_t quote_size = 0;
    uint8_t *quote_buf = nullptr;

    BIO *bio = BIO_new(BIO_s_mem());
    BIO_write(bio, der_crt, crt_size);
    X509 *x509 = PEM_read_bio_X509(bio, NULL, NULL, NULL);
    if (!x509) {
        grpc_printf("parse crt failed!\n");
        ret = -1;
        goto out;
    }

    // parse quote
    ret = dummy_parse_quote(x509, &quote_buf, quote_size);
    if (ret != 0) {
        grpc_printf("parse quote failed!\n");
        goto out;
    }

    // verify quote
    ret = dummy_verify_quote(quote_buf, quote_size-SHA256_DIGEST_LENGTH);
    if (ret != 0) {
        grpc_printf("verify quote failed!\n");
        goto out;
    }

    // verify hash
    ret = verify_pubkey_hash(x509, quote_buf+quote_size-SHA256_DIGEST_LENGTH, SHA256_DIGEST_LENGTH);
    if (ret != 0) {
        grpc_printf("verify pubkey hash failed!\n");
        goto out;
    }

out:
    BIO_free(bio);
    return ret;
}

ra_tls_measurement dummy_parse_measurement(const char *der_crt, size_t len) {
    return ra_tls_measurement();
}

} // namespace sgx
} // namespace grpc

// #endif // SGX_RA_TLS_DUMMY_BACKEND
