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

#if defined (SGX_RA_TLS_AZURE_TDX_BACKEND)

#include <grpcpp/security/sgx/sgx_ra_tls_backends.h>
#include <grpcpp/security/sgx/sgx_ra_tls_impl.h>

#include <stdio.h>
#include <vector>
#include <string>
#include <assert.h>
#include <fstream>
#include <cstring>

#include <azguestattestation1/AttestationClient.h>
#include "attest_utils/Logger.h"

#include <nlohmann/json.hpp>
#include <chrono>
#include "attest_utils/Utils.h"
#include "attest_utils/AttestClient.h"
#include "attest_utils/HttpClient.h"
#include "boost/algorithm/hex.hpp"

namespace grpc {
namespace sgx {

#include <tdx_attest.h>

using json = nlohmann::json;
using namespace std;
using namespace std::chrono;

const uint8_t g_att_key_id_list[256] = {0};

static void tdx_gen_report_data(uint8_t *reportdata) {
    srand(time(NULL));
    for (int i = 0; i < TDX_REPORT_DATA_SIZE; i++) {
        reportdata[i] = rand();
    }
}

// input:  uint8_t *hash
// output: uint8_t **quote_buf
//             Format
//                 0-3: quote size
//                 4-7: claims size
//                 8: start of quote data
//                 8 + quote size: start of claims data
// output: uint32_t &quote_size
static int tdx_generate_quote(
        uint8_t **quote_buf, uint32_t &quote_size, uint8_t *hash) {

  int ret = 0; // error

  try {
    AttestationClient *attestation_client = nullptr;
    Logger *log_handle = new Logger();

    // Initialize attestation client
    if (!Initialize(log_handle, &attestation_client)) {
      grpc_fprintf(stderr, "Error: Failed to create attestation client object\n\n");
      Uninitialize();
      return(ret);
    }
    attest::AttestationResult result;

    auto start = high_resolution_clock::now();

    // Check if vTPM NV index for user-data exists.
    std::string tpm_nvreadpublic_cmd = "tpm2_nvreadpublic 0x01400002 > /dev/null 2>&1";
    uint8_t ret_code = system(tpm_nvreadpublic_cmd.c_str());
    if (ret_code != 0) {
        // Create NV index, since it doesn't exist.
        std::string tpm_nvdefine_cmd = "tpm2_nvdefine -C o 0x01400002 -s 64";
        uint8_t ret_code = system(tpm_nvdefine_cmd.c_str());
        if (ret_code != 0) {
            cout << "Error: Failed to create NV index." << endl;
            return(ret);
        }
    }

    // Convert hash to hex string.
    std::ostringstream user_data;
    user_data << std::hex << std::setfill('0');
    for (size_t i = 0; i < SHA256_DIGEST_LENGTH; ++i) {
        user_data << std::setw(2) << static_cast<int>(hash[i]);
    }

    // Write hash as user-data to vTPM before retrieving evidence.
    // This adds the hash as user-data to the TPM report runtime data and
    // binds the hash to the TD report/quote.
    std::ostringstream tpm_write_cmd;
    tpm_write_cmd << "echo " << user_data.str() << " | xxd -r -p | tpm2_nvwrite -C o 0x1400002 -i -";
    ret_code = system(tpm_write_cmd.str().c_str());
    if (ret_code != 0) {
        cout << "Error: Failed to write user-data to TPM, ret_code = " << ret_code << endl;
        return(ret);
    }

    // Retrieve evidence from vTPM.
    unsigned char *evidence = nullptr;
    result = attestation_client->GetHardwarePlatformEvidence(&evidence);

    auto stop = high_resolution_clock::now();
    duration<double, std::milli> elapsed = stop - start;

    if (result.code_ != attest::AttestationResult::ErrorCode::SUCCESS) {
      grpc_fprintf(stderr, "Error: Failed to get quote\n\n");
      Uninitialize();
      return(ret);
    }

    std::string quote_data;
    quote_data = reinterpret_cast<char *>(evidence);

    // Parses the returned json response
    json json_response = json::parse(quote_data);

    std::string encoded_quote = json_response["quote"];
    if (encoded_quote.empty()) {
      result.code_ = attest::AttestationResult::ErrorCode::ERROR_EMPTY_TD_QUOTE;
      result.description_ = std::string("Error: Empty Quote received from IMDS Quote Endpoint");
      Uninitialize();
      return(ret);
    }

    std::string encoded_claims = json_response["runtimeData"]["data"];
    if (encoded_claims.empty()) {
      result.code_ = attest::AttestationResult::ErrorCode::ERROR_EMPTY_TD_QUOTE;
      result.description_ = std::string("Error: Empty Claims received from IMDS Quote Endpoint");
      Uninitialize();
      return(ret);
    }

    // decode the base64url encoded quote and claims to raw bytes
    std::vector<unsigned char> quote_bytes = Utils::base64url_to_binary(encoded_quote);
    std::vector<unsigned char> claims_bytes = Utils::base64url_to_binary(encoded_claims);

    quote_size = quote_bytes.size();
    uint32_t claims_size = claims_bytes.size();
    *quote_buf = (uint8_t *)realloc(*quote_buf, quote_size + claims_size + 8);
    memcpy(*quote_buf, (uint8_t *)&quote_size, 4);
    memcpy(*quote_buf + 4, (uint8_t *)&claims_size, 4);
    memcpy(*quote_buf + 8, (uint8_t *)quote_bytes.data(), quote_size);
    memcpy(*quote_buf + 8 + quote_size, (uint8_t *)claims_bytes.data(), claims_size);
    quote_size += claims_size + 8;

    cout << "Info: Generated TDX quote and claims data.\n" << endl;
    //print_hex_dump("\nInfo: Generated TDX quote and claims data\n", " ", *quote_buf, quote_size);

    Uninitialize();

    ret = 1; // success
  }
  catch (std::exception &e) {
    cout << "Error: Exception occured. Details - " << e.what() << endl;
    return(ret);
  }

  return(ret);
};

std::vector<std::string> tdx_generate_key_cert() {
    return generate_key_cert(tdx_generate_quote);
}

void tdx_verify_init() {
    generate_key_cert(dummy_generate_quote);
};

ra_tls_measurement tdx_parse_measurement(const char *der_crt, size_t len) {
    // TODO
    return ra_tls_measurement();
}

int tdx_parse_quote(X509 *x509, uint8_t **quote, uint32_t &quote_size) {
    return parse_quote(x509, quote, quote_size);
};

static void deleteFiles(const std::vector<std::string>& filenames) {
    // Loop through the array of filenames and delete each file
    for (const std::string& filename : filenames)
        // Silently delete files
        std::remove(filename.c_str());
}

// input:  uint8_t *quote_buf
// input:  size_t quote_size
// output: uint8_t ** hash_buf
int tdx_verify_quote(uint8_t *quote_buf, size_t quote_size, uint8_t **hash_buf) {
  int ret = -1; // error

  try {
    std::string config_filename = "/etc/attest_config.json";

    // set attestation request based on config file
    std::ifstream config_file(config_filename);
    json config;
    if (config_file.is_open()) {
      config = json::parse(config_file);
      config_file.close();
    } else {
        grpc_fprintf(stderr, "Error: Failed to open config file\n\n");
        return(ret);
    }

    std::string attestation_url;
    if (!config.contains("attestation_url")) {
      grpc_fprintf(stderr, "Error: attestation_url is missing\n\n");
      return(ret);
    }
    attestation_url = config["attestation_url"];

    std::string api_key;
    if (config.contains("api_key")) {
      api_key = config["api_key"];
    }

    bool metrics_enabled = false;
    if (config.contains("enable_metrics")) {
      metrics_enabled = config["enable_metrics"];
    }

    std::string provider;
    if (!config.contains("attestation_provider")) {
      grpc_fprintf(stderr, "Error: attestation_provider is missing\n\n");
      return(ret);
    }
    provider = config["attestation_provider"];

    if (!Utils::case_insensitive_compare(provider, "ita") &&
        !Utils::case_insensitive_compare(provider, "maa")) {
      grpc_fprintf(stderr, "Error: attestation_provider is invalid\n\n");
      return(ret);
    }

    // check for user claims
    std::string client_payload;
    json user_claims = config["claims"];
    if (!user_claims.is_null()) {
      client_payload = user_claims.dump();
    }

    // if attesting with Amber, we need to make sure an API token was provided
    if (api_key.empty() && Utils::case_insensitive_compare(provider, "ita")) {
      grpc_fprintf(stderr, "Error: Attestation endpoint \"api_key\" value missing\n\n");
      return(ret);
    }

    cout << "Info: Received TDX quote and claims data.\n" << endl;
    //print_hex_dump("\nInfo: Received TDX quote and claims data\n", " ", quote_buf, quote_size);

    uint32_t q_size = *(uint32_t*)quote_buf;
    uint32_t claims_size = *(uint32_t*)(quote_buf + 1);
    std::vector<unsigned char> quote_vector(quote_buf + 8, quote_buf + 8 + q_size);
    std::string encoded_quote = Utils::binary_to_base64url(quote_vector);
    std::vector<unsigned char> claims_vector(quote_buf + 8 + q_size, quote_buf + quote_size);
    std::string encoded_claims = Utils::binary_to_base64url(claims_vector);

    HttpClient http_client;
    AttestClient::Config attestation_config = {
        attestation_url,
        provider,
        encoded_quote,
        encoded_claims,
        api_key};

    auto start = high_resolution_clock::now();
    std::string jwt_token = AttestClient::VerifyEvidence(attestation_config, http_client);
    auto stop = high_resolution_clock::now();
    duration<double, std::milli> token_elapsed = stop - start;

    if (jwt_token.empty()) {
      fprintf(stderr, "Error: Empty token received\n");
      return(ret);
    }

    // Parse TEE-specific claims from JSON Web Token
    std::vector<std::string> tokens;
    boost::split(tokens, jwt_token, [](char c) {return c == '.'; });
    if (tokens.size() < 3) {
      fprintf(stderr, "Error: Invalid JWT token\n");
      return(ret);
    }

    json attestation_claims = json::parse(Utils::base64_decode(tokens[1]));
    int indent = 4;
    cout << "Info: Attestation claims:\n" << attestation_claims.dump(indent) << endl;

    try {
        std::string user_data;
        if (Utils::case_insensitive_compare(provider, "maa"))
            user_data = attestation_claims["x-ms-runtime"]["user-data"].get<std::string>();
        else if (Utils::case_insensitive_compare(provider, "ita"))
            user_data = attestation_claims["attester_runtime_data"]["user-data"].get<std::string>();
        // Return the public key hash from user-data.
        std::string unhex_user_data = boost::algorithm::unhex(user_data);
        std::vector<unsigned char> hash_vector(unhex_user_data.begin(), unhex_user_data.end());
        *hash_buf = (uint8_t *)realloc(*hash_buf, SHA256_DIGEST_LENGTH);
        memcpy(*hash_buf, (uint8_t *)hash_vector.data(), SHA256_DIGEST_LENGTH);
        print_hex_dump("\nInfo: Public key hash from user-data:\n", " ", *hash_buf, SHA256_DIGEST_LENGTH);
    }
    catch (...) {
        fprintf(stderr, "Error: JWT missing TD report custom data\n");
        return(ret);
    }

    ret = 0; // success
  }
  catch (std::exception &e) {
    cout << "Error: Exception occured. Details - " << e.what() << endl;
    return(ret);
  }

  return(ret);
};

// input: size_t len
int tdx_verify_cert(const char *der_crt, size_t len) {
    int ret = 0;
    uint32_t quote_size = 0;
    uint8_t *quote_buf = nullptr;
    uint8_t *hash_buf = nullptr;

    BIO *bio = BIO_new(BIO_s_mem());
    BIO_write(bio, der_crt, len);
    X509 *x509 = PEM_read_bio_X509(bio, NULL, NULL, NULL);
    if (!x509) {
        grpc_printf("Error: Failed to parse certificate.\n");
        goto out;
    }

    ret = tdx_parse_quote(x509, &quote_buf, quote_size);
    if (ret != 0) {
        grpc_printf("Error: Failed to parse quote.\n");
        goto out;
    }

    ret = tdx_verify_quote(quote_buf, quote_size, &hash_buf);
    if (ret != 0) {
        grpc_printf("Error: Failed to verify quote.\n");
        goto out;
    }

    ret = verify_pubkey_hash(x509, hash_buf, SHA256_DIGEST_LENGTH);
    if (ret != 0) {
        grpc_printf("Error: Failed to verify public key hash.\n");
        goto out;
    }

    cout << "\nInfo: Public key hash from user-data and X509 cert match.\n" << endl; 

    // ret = verify_measurement((const char *)&p_rep_body->mr_enclave,
    //                          (const char *)&p_rep_body->mr_signer,
    //                          (const char *)&p_rep_body->isv_prod_id,
    //                          (const char *)&p_rep_body->isv_svn);

out:
    BIO_free(bio);
    return ret;
}

} // namespace sgx
} // namespace grpc

#endif
