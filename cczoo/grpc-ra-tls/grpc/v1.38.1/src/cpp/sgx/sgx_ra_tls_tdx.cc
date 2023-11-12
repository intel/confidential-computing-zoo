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

#if defined(SGX_RA_TLS_TDX_BACKEND) || defined (SGX_RA_TLS_AZURE_TDX_BACKEND) || defined (SGX_RA_TLS_GCP_TDX_BACKEND)

#include <grpcpp/security/sgx/sgx_ra_tls_backends.h>
#include <grpcpp/security/sgx/sgx_ra_tls_impl.h>
#include <stdio.h>
#include <vector>
#include <string>
#include <assert.h>
#include <fstream>
#include <cstring>

#ifdef SGX_RA_TLS_AZURE_TDX_BACKEND
#include <azguestattestation1/AttestationClient.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include "azure_tdx/Utils.h"
#include "azure_tdx/Logger.h"
#include "azure_tdx/AttestClient.h"
#include "azure_tdx/HttpClient.h"
#endif

#ifdef SGX_RA_TLS_GCP_TDX_BACKEND
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
using json = nlohmann::json;
using namespace std;
typedef unsigned char BYTE;
#endif

#ifdef SGX_RA_TLS_TDX_BACKEND
#include "sgx_urts.h"
#endif

namespace grpc {
namespace sgx {

#include <tdx_attest.h>

#ifdef SGX_RA_TLS_TDX_BACKEND
#include <sgx_ql_quote.h>
#include <sgx_dcap_quoteverify.h>
#endif

#ifdef SGX_RA_TLS_AZURE_TDX_BACKEND
using json = nlohmann::json;
using namespace std;
using namespace std::chrono;
#endif

const uint8_t g_att_key_id_list[256] = {0};

static void tdx_gen_report_data(uint8_t *reportdata) {
    srand(time(NULL));
    for (int i = 0; i < TDX_REPORT_DATA_SIZE; i++) {
        reportdata[i] = rand();
    }
}


#ifdef SGX_RA_TLS_AZURE_TDX_BACKEND
static int tdx_generate_quote(
        uint8_t **quote_buf, uint32_t &quote_size, uint8_t *hash) {

  int ret = -1;

  try {
    AttestationClient *attestation_client = nullptr;
    Logger *log_handle = new Logger();

    // Initialize attestation client
    if (!Initialize(log_handle, &attestation_client)) {
      grpc_fprintf(stderr, "Failed to create attestation client object\n\n");
      Uninitialize();
      return(0);
    }
    attest::AttestationResult result;

    auto start = high_resolution_clock::now();

    unsigned char *evidence = nullptr;
    result = attestation_client->GetHardwarePlatformEvidence(&evidence);

    auto stop = high_resolution_clock::now();
    duration<double, std::milli> elapsed = stop - start;

    if (result.code_ != attest::AttestationResult::ErrorCode::SUCCESS) {
      grpc_fprintf(stderr, "Failed to get quote\n\n");
      Uninitialize();
      return(0);
    }

    std::string quote_data;
    quote_data = reinterpret_cast<char *>(evidence);

    // Parses the returned json response
    json json_response = json::parse(quote_data);

    std::string encoded_quote = json_response["quote"];
    if (encoded_quote.empty()) {
      result.code_ = attest::AttestationResult::ErrorCode::ERROR_EMPTY_TD_QUOTE;
      result.description_ = std::string("Empty Quote received from IMDS Quote Endpoint");
      Uninitialize();
      return(0);
    }

    // decode the base64url encoded quote to raw bytes
    std::vector<unsigned char> quote_bytes = Utils::base64url_to_binary(encoded_quote);

    quote_size = quote_bytes.size();
    *quote_buf = (uint8_t *)realloc(*quote_buf, quote_size+SHA256_DIGEST_LENGTH);
    memcpy(*quote_buf, (uint8_t *)quote_bytes.data(), quote_size);
    memcpy((*quote_buf)+quote_size, hash, SHA256_DIGEST_LENGTH);
    quote_size += SHA256_DIGEST_LENGTH;

    print_hex_dump("tdx_generate_quote: TDX quote data\n", " ", *quote_buf, quote_size);

    Uninitialize();
  }
  catch (std::exception &e) {
    cout << "Exception occured. Details - " << e.what() << endl;
    return(0);
  }

  return ret;
};
#elif SGX_RA_TLS_GCP_TDX_BACKEND
 static int tdx_generate_quote(
         uint8_t **quote_buf, uint32_t &quote_size, uint8_t *hash) {

    int ret = -1;

    std::string config_filename = "/etc/gcp_tdx_config.json";

    // set attestation request based on config file
    std::ifstream config_file(config_filename);
    json config;
    if (config_file.is_open()) {
      config = json::parse(config_file);
      config_file.close();
    } else {
        grpc_fprintf(stderr, "Failed to open config file\n\n");
        return(ret);
    }

    std::string attest_cmd;
    if (!config.contains("attest_cmd")) {
      grpc_fprintf(stderr, "Attest cmd is missing\n\n");
      return(ret);
    }
    attest_cmd = config["attest_cmd"];

    std::string quote_location;
    if (!config.contains("quote_location")) {
      grpc_fprintf(stderr, "quote location is missing\n\n");
      return(ret);
    }
    quote_location = config["quote_location"];
    try {
    uint8_t ret_code = system(attest_cmd.c_str());

    if (ret_code == 0) {
        cout << "attest command executed successfully" << endl;
    }
    else {
        cout << "attest command execution failed or returned "
        "non-zero: " << ret_code << endl;
        return(0);
    }

    if (WEXITSTATUS(ret_code) == 0x0) {
          
    // decode quote to raw bytes
    // open the file:
    std::basic_ifstream<BYTE> file(quote_location, std::ios::binary);

    // read the data:
    std::vector<unsigned char> quote_bytes = std::vector<BYTE>((std::istreambuf_iterator<BYTE>(file)),
                              std::istreambuf_iterator<BYTE>());


    quote_size = quote_bytes.size();
    *quote_buf = (uint8_t *)realloc(*quote_buf, quote_size+SHA256_DIGEST_LENGTH);
    memcpy(*quote_buf, (uint8_t *)quote_bytes.data(), quote_size);
    memcpy((*quote_buf)+quote_size, hash, SHA256_DIGEST_LENGTH);
    quote_size += SHA256_DIGEST_LENGTH;

    print_hex_dump("tdx_generate_quote: TDX quote data\n", " ", *quote_buf, quote_size);
    
     }
    }
    catch (std::exception &e) {
     cout << "Exception occured. Details - " << e.what() << endl;
     return(0);
    }

   return ret;
 };
#else
static int tdx_generate_quote(
        uint8_t **quote_buf, uint32_t &quote_size, uint8_t *hash) {
    int ret = -1;

    tdx_report_data_t report_data = {{0}};
    tdx_report_t tdx_report = {{0}};
    tdx_uuid_t selected_att_key_id = {0};

    tdx_gen_report_data(report_data.d);
    // print_hex_dump("TDX report data\n", " ", report_data.d, sizeof(report_data.d));

    if (TDX_ATTEST_SUCCESS != tdx_att_get_report(&report_data, &tdx_report)) {
        grpc_fprintf(stderr, "failed to get the report.\n");
        ret = 0;
    }
    // print_hex_dump("TDX report\n", " ", tdx_report.d, sizeof(tdx_report.d));

    if (TDX_ATTEST_SUCCESS != tdx_att_get_quote(&report_data, NULL, 0, &selected_att_key_id,
        quote_buf, &quote_size, 0)) {
        grpc_fprintf(stderr, "failed to get the quote.\n");
        ret = 0;
    }
    // print_hex_dump("TDX quote data\n", " ", *quote_buf, quote_size);

    // printf("tdx_generate_quote, sizeof %d, quote_size %d\n", sizeof(*quote_buf), quote_size);

    realloc(*quote_buf, quote_size+SHA256_DIGEST_LENGTH);
    memcpy((*quote_buf)+quote_size, hash, SHA256_DIGEST_LENGTH);
    quote_size += SHA256_DIGEST_LENGTH;

    // printf("tdx_generate_quote, sizeof %d, quote_size %d\n", sizeof(*quote_buf), quote_size);
    return ret;
};
#endif

std::vector<std::string> tdx_generate_key_cert() {
    return generate_key_cert(tdx_generate_quote);
}

int tdx_parse_quote(X509 *x509, uint8_t **quote, uint32_t &quote_size) {
    return parse_quote(x509, quote, quote_size);
};

void tdx_verify_init() {
    generate_key_cert(dummy_generate_quote);
};

#ifdef SGX_RA_TLS_AZURE_TDX_BACKEND
int tdx_verify_quote(uint8_t *quote_buf, size_t quote_size) {
  int ret = -1;

  try {
    std::string config_filename = "/etc/azure_tdx_config.json";

    // set attestation request based on config file
    std::ifstream config_file(config_filename);
    json config;
    if (config_file.is_open()) {
      config = json::parse(config_file);
      config_file.close();
    } else {
        grpc_fprintf(stderr, "Failed to open config file\n\n");
        return(ret);
    }

    std::string attestation_url;
    if (!config.contains("attestation_url")) {
      grpc_fprintf(stderr, "Attestation_url is missing\n\n");
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
      grpc_fprintf(stderr, "Attestation_provider is missing\n\n");
      return(ret);
    }
    provider = config["attestation_provider"];

    if (!Utils::case_insensitive_compare(provider, "amber") &&
        !Utils::case_insensitive_compare(provider, "maa")) {
      grpc_fprintf(stderr, "Attestation provider was incorrect\n\n");
      return(ret);
    }

    std::map<std::string, std::string> hash_type;
    hash_type["maa"] = "sha256";
    hash_type["amber"] = "sha512";

    // check for user claims
    std::string client_payload;
    json user_claims = config["claims"];
    if (!user_claims.is_null()) {
      client_payload = user_claims.dump();
    }

    // if attesting with Amber, we need to make sure an API token was provided
    if (api_key.empty() && Utils::case_insensitive_compare(provider, "amber")) {
      grpc_fprintf(stderr, "Attestation endpoint \"api_key\" value missing\n\n");
      return(ret);
    }

    print_hex_dump("tdx_verify_quote: TDX quote data\n", " ", quote_buf, quote_size);

    std::vector<unsigned char> quote_vector(quote_buf, quote_buf + quote_size);
    std::string encoded_quote = Utils::binary_to_base64url(quote_vector);

    // For now, pass empty claim
    std::string json_claims = "{}";
    std::vector<unsigned char> claims_vector(json_claims.begin(), json_claims.end());
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
      fprintf(stderr, "Empty token received\n");
      return(ret);
    }

    grpc_printf("Info: App: Verification completed successfully.\n");

    return(0);
  }
  catch (std::exception &e) {
    cout << "Exception occured. Details - " << e.what() << endl;
    return(1);
  }
};
#elif SGX_RA_TLS_GCP_TDX_BACKEND
int tdx_verify_quote(uint8_t *quote_buf, size_t quote_size) {
   int ret = -1;
   std::string config_filename = "/etc/gcp_tdx_config.json";

    // set attestation request based on config file
    std::ifstream config_file(config_filename);
    json config;
    if (config_file.is_open()) {
      config = json::parse(config_file);
      config_file.close();
    } else {
        grpc_fprintf(stderr, "Failed to open config file\n\n");
        return(ret);
    }

    std::string verify_cmd;
    if (!config.contains("verify_cmd")) {
      grpc_fprintf(stderr, "verify cmd is missing\n\n");
      return(ret);
    }
    verify_cmd = config["verify_cmd"];

    try {
    uint8_t ret_code = system(verify_cmd.c_str());

    if (ret_code == 0) {
	cout << "verify command executed successfully\n" << endl;
    }
    else {
	cout << "verify command execution failed or returned "
        "non-zero: " << ret_code << endl;
	return(ret);
    }
    
    if (WEXITSTATUS(ret_code) == 0x0) {
	cout << "quote verified\n" << endl;
        return(0);
    }
    else {
	cout << "quote not verified\n" << endl;
        return(ret);
    }

   }
   catch (std::exception &e) {
     cout << "Exception occured. Details - " << e.what() << endl;
     return(1);
   }

   return ret;
 };
#else
int tdx_verify_quote(uint8_t *quote_buf, size_t quote_size) {
    bool use_qve = false;
    (void)(use_qve);

    int ret = 0;
    time_t current_time = 0;
    uint32_t supplemental_data_size = 0;
    uint8_t *p_supplemental_data = nullptr;

    quote3_error_t dcap_ret = SGX_QL_ERROR_UNEXPECTED;
    sgx_ql_qv_result_t quote_verification_result = SGX_QL_QV_RESULT_UNSPECIFIED;
    uint32_t collateral_expiration_status = 1;

    sgx_status_t sgx_ret = SGX_SUCCESS;
    uint8_t rand_nonce[16] = "59jslk201fgjmm;";
    sgx_ql_qe_report_info_t qve_report_info;
    sgx_launch_token_t token = { 0 };

    int updated = 0;
    quote3_error_t verify_qveid_ret = SGX_QL_ERROR_UNEXPECTED;
    sgx_enclave_id_t eid = 0;

    // call DCAP quote verify library to get supplemental data size
    dcap_ret = tdx_qv_get_quote_supplemental_data_size(&supplemental_data_size);
    if (dcap_ret == SGX_QL_SUCCESS && \
        supplemental_data_size == sizeof(sgx_ql_qv_supplemental_t)) {
        grpc_printf("Info: tdx_qv_get_quote_supplemental_data_size successfully returned.\n");
        p_supplemental_data = (uint8_t*)malloc(supplemental_data_size);
    } else {
        grpc_printf("Error: tdx_qv_get_quote_supplemental_data_size failed: 0x%04x\n", dcap_ret);
        supplemental_data_size = 0;
    }

    // set current time. This is only for sample purposes, in production mode a trusted time should be used.
    current_time = time(NULL);

    // call DCAP quote verify library for quote verification
    print_hex_dump("TDX parse quote data\n", " ", quote_buf, quote_size);
    dcap_ret = tdx_qv_verify_quote(
            quote_buf, quote_size,
            NULL,
            current_time,
            &collateral_expiration_status,
            &quote_verification_result,
            NULL,
            supplemental_data_size,
            p_supplemental_data);
    if (dcap_ret == SGX_QL_SUCCESS) {
        grpc_printf("Info: App: tdx_qv_verify_quote successfully returned.\n");
    } else {
        grpc_printf("Error: App: tdx_qv_verify_quote failed: 0x%04x\n", dcap_ret);
    }

    //check verification result
    switch (quote_verification_result) {
        case SGX_QL_QV_RESULT_OK:
            //check verification collateral expiration status
            //this value should be considered in your own attestation/verification policy
            //
            if (collateral_expiration_status == 0) {
                grpc_printf("Info: App: Verification completed successfully.\n");
                ret = 0;
            } else {
                grpc_printf("Warning: App: Verification completed, but collateral is out of date based on 'expiration_check_date' you provided.\n");
                ret = 1;
            }
            break;
        case SGX_QL_QV_RESULT_CONFIG_NEEDED:
        case SGX_QL_QV_RESULT_OUT_OF_DATE:
        case SGX_QL_QV_RESULT_OUT_OF_DATE_CONFIG_NEEDED:
        case SGX_QL_QV_RESULT_SW_HARDENING_NEEDED:
        case SGX_QL_QV_RESULT_CONFIG_AND_SW_HARDENING_NEEDED:
            grpc_printf("Warning: App: Verification completed with Non-terminal result: %x\n", quote_verification_result);
            ret = 1;
            break;
        case SGX_QL_QV_RESULT_INVALID_SIGNATURE:
        case SGX_QL_QV_RESULT_REVOKED:
        case SGX_QL_QV_RESULT_UNSPECIFIED:
        default:
            grpc_printf("Error: App: Verification completed with Terminal result: %x\n", quote_verification_result);
            ret = -1;
            break;
    }

    return ret;
}
#endif

int tdx_verify_cert(const char *der_crt, size_t len) {
    int ret = 0;
    uint32_t quote_size = 0;
    uint8_t *quote_buf = nullptr;

    BIO *bio = BIO_new(BIO_s_mem());
    BIO_write(bio, der_crt, len);
    X509 *x509 = PEM_read_bio_X509(bio, NULL, NULL, NULL);
    if (!x509) {
        grpc_printf("parse the crt failed.\n");
        goto out;
    }

    ret = tdx_parse_quote(x509, &quote_buf, quote_size);
    if (ret != 0) {
        grpc_printf("parse quote failed.\n");
        goto out;
    }

    ret = tdx_verify_quote(quote_buf, quote_size-SHA256_DIGEST_LENGTH);
    if (ret != 0) {
        grpc_printf("verify quote failed.\n");
        goto out;
    }

    ret = verify_pubkey_hash(x509, quote_buf+quote_size-SHA256_DIGEST_LENGTH, SHA256_DIGEST_LENGTH);
    if (ret != 0) {
        grpc_printf("verify the public key hash failed.\n");
        goto out;
    }

    // ret = verify_measurement((const char *)&p_rep_body->mr_enclave,
    //                          (const char *)&p_rep_body->mr_signer,
    //                          (const char *)&p_rep_body->isv_prod_id,
    //                          (const char *)&p_rep_body->isv_svn);

out:
    BIO_free(bio);
    return ret;
}

ra_tls_measurement tdx_parse_measurement(const char *der_crt, size_t len) {
    // TODO
    return ra_tls_measurement();
}

} // namespace sgx
} // namespace grpc

#endif // SGX_RA_TLS_TDX_BACKEND || SGX_RA_TLS_AZURE_TDX_BACKEND
