/*
 *
 * Copyright 2019 gRPC authors.
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

#include <grpc/support/log.h>
#include <grpc/support/sync.h>
#include <grpcpp/security/server_credentials.h>
#include "grpc_sgx_ra_tls_utils.h"
#include "grpc_sgx_credentials_provider.h"

namespace grpc {
namespace sgx {

#define PEM_BEGIN_CRT           "-----BEGIN CERTIFICATE-----\n"
#define PEM_END_CRT             "-----END CERTIFICATE-----\n"


// Server side is required to use a provider, because server always needs to use identity certs.
std::vector<std::string> get_cred_key_pair() {
  std::vector<std::string> key_cert;
  unsigned char private_key_pem[16000], cert_pem[16000];
  uint8_t *der_key = nullptr, *der_crt = nullptr;
  size_t der_key_size, der_crt_size, olen;
  std::string error = "";

  mbedtls_pk_context pkey;
  mbedtls_x509_crt srvcert;
  mbedtls_ctr_drbg_context ctr_drbg;

  mbedtls_pk_init(&pkey);
  mbedtls_x509_crt_init(&srvcert);
  mbedtls_ctr_drbg_init(&ctr_drbg);

  library_engine ra_tls_attest_lib("libra_tls_attest.so", RTLD_LAZY);
  auto ra_tls_create_key_and_crt_der_f =
    reinterpret_cast<int (*)(uint8_t**, size_t*, uint8_t**, size_t*)>(
      ra_tls_attest_lib.get_func("ra_tls_create_key_and_crt_der"));

  int ret = (*ra_tls_create_key_and_crt_der_f)(&der_key, &der_key_size, &der_crt, &der_crt_size);
  if (ret != 0) {
    error = "ra_tls_get_key_cert->ra_tls_create_key_and_crt_der_f";
    goto out;
  }

  ret = mbedtls_x509_crt_parse(&srvcert, (unsigned char*)der_crt, der_crt_size);
  if (ret != 0) {
    error = "ra_tls_get_key_cert->mbedtls_x509_crt_parse";
    goto out;
  }

  ret = mbedtls_pk_parse_key(&pkey, (unsigned char*)der_key, der_key_size, /*pwd=*/NULL, 0,
                              mbedtls_ctr_drbg_random, &ctr_drbg);
  if (ret != 0) {
    error = "ra_tls_get_key_cert->mbedtls_pk_parse_key";
    goto out;
  }

  ret = mbedtls_pk_write_key_pem(&pkey, private_key_pem, 16000);
  if (ret != 0) {
    error = "ra_tls_get_key_cert->mbedtls_pk_write_key_pem";
    goto out;
  }

  ret = mbedtls_pem_write_buffer(PEM_BEGIN_CRT, PEM_END_CRT,
                                 srvcert.raw.p, srvcert.raw.len,
                                 cert_pem, 16000, &olen);
  if (ret != 0) {
    error = "ra_tls_get_key_cert->mbedtls_pem_write_buffer";
    goto out;
  };

  key_cert.emplace_back(std::string((char*) private_key_pem));
  key_cert.emplace_back(std::string((char*) cert_pem));

  // mbedtls_printf("Server key:\n%s\n", private_key_pem);
  // mbedtls_printf("Server crt:\n%s\n", cert_pem);

  out:
    mbedtls_pk_free(&pkey);
    mbedtls_x509_crt_free(&srvcert);
    mbedtls_ctr_drbg_free(&ctr_drbg);
    check_free(der_key);
    check_free(der_crt);

    if (ret != 0) {
      throw std::runtime_error(
            std::string((error + std::string(" failed: %s\n")).c_str(), mbedtls_high_level_strerr(ret)));
    }

  fflush(stdout);
  return key_cert;
}

std::shared_ptr<grpc::ServerCredentials> TlsServerCredentials() {
  using namespace ::grpc_impl::experimental;
  auto key_pair = get_cred_key_pair();
  auto provider = GetCredentialsProvider(key_pair[0], key_pair[1]);
  auto server_creds = provider->GetServerCredentials(kTlsCredentialsType);
  auto processor = std::shared_ptr<AuthMetadataProcessor>();
  server_creds->SetAuthMetadataProcessor(processor);
  return server_creds;
};

}  // namespace sgx
}  // namespace grpc
