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

#ifndef SGX_RA_TLS_IMPL_H
#define SGX_RA_TLS_IMPL_H

#include <grpcpp/security/sgx/sgx_ra_tls_context.h>
// #include <grpcpp/security/sgx/sgx_ra_tls_utils.h>

namespace grpc {
namespace sgx {

#include <openssl/evp.h>
#include <openssl/rsa.h>
#include <openssl/x509.h>
#include <openssl/x509v3.h>
#include <openssl/sha.h>
#include <openssl/pem.h>
#include <openssl/asn1.h>

extern const char * RA_TLS_SHORT_NAME;
extern const char * RA_TLS_LONG_NAME;

ra_tls_config parse_config_json(const char* file);

std::vector<std::string> generate_key_cert(
    int (*generate_quote)(
        uint8_t **quote_buf, uint32_t &quote_size, uint8_t *hash));

int parse_quote(X509 *x509, uint8_t **quote, uint32_t &quote_size);

int verify_pubkey_hash(X509 *x509, uint8_t *pubkey_hash, uint32_t hash_size);

#ifdef SGX_RA_TLS_TDX_BACKEND

int verify_measurement(const char* mr_seam,
                       const char* mrsigner_seam,
                       const char* mr_td,
                       const char* mr_config_id,
                       const char* mr_owner,
                       const char* mr_owner_config,
                       const char* rt_mr0,
                       const char* rt_mr1,
                       const char* rt_mr2,
                       const char* rt_mr3);

#else

int verify_measurement(const char* mr_enclave, const char* mr_signer,
                       const char* isv_prod_id, const char* isv_svn);

#endif

} // namespace sgx
} // namespace grpc

#endif // SGX_RA_TLS_IMPL_H