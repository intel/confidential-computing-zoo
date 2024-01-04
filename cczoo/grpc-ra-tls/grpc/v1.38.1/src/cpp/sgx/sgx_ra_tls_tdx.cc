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
#include "attest_utils/Logger.h"
#endif

#ifdef SGX_RA_TLS_GCP_TDX_BACKEND
#include <iostream>
#include <sstream>
#include <iomanip>
using namespace std;
typedef unsigned char BYTE;
#endif

#if defined (SGX_RA_TLS_AZURE_TDX_BACKEND) || defined (SGX_RA_TLS_GCP_TDX_BACKEND)
#include <nlohmann/json.hpp>
#include <chrono>
#include "attest_utils/Utils.h"
#include "attest_utils/AttestClient.h"
#include "attest_utils/HttpClient.h"
#include "boost/algorithm/hex.hpp"
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

#if defined (SGX_RA_TLS_AZURE_TDX_BACKEND) || defined (SGX_RA_TLS_GCP_TDX_BACKEND)
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

void tdx_verify_init() {
    generate_key_cert(dummy_generate_quote);
};

ra_tls_measurement tdx_parse_measurement(const char *der_crt, size_t len) {
    // TODO
    return ra_tls_measurement();
}

static void deleteFiles(const std::vector<std::string>& filenames) {
    // Loop through the array of filenames and delete each file
    for (const std::string& filename : filenames)
        // Silently delete files
        std::remove(filename.c_str());
}

#if defined (SGX_RA_TLS_AZURE_TDX_BACKEND) || defined (SGX_RA_TLS_GCP_TDX_BACKEND)
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
#ifdef SGX_RA_TLS_GCP_TDX_BACKEND
            user_data = attestation_claims["attester_held_data"].get<std::string>();
            user_data = Utils::base64_decode(user_data);
#else
            user_data = attestation_claims["attester_runtime_data"]["user-data"].get<std::string>();
#endif
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

    ret = parse_quote(x509, &quote_buf, quote_size);
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
#endif

#ifdef SGX_RA_TLS_AZURE_TDX_BACKEND
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
#endif // SGX_RA_TLS_AZURE_TDX_BACKEND

#ifdef SGX_RA_TLS_GCP_TDX_BACKEND
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
    // Convert hash to hex string.
    std::ostringstream user_data;
    user_data << std::hex << std::setfill('0');
    for (size_t i = 0; i < SHA256_DIGEST_LENGTH; ++i) {
        user_data << std::setw(2) << static_cast<int>(hash[i]);
    }

    std::string encoded_user_data = Utils::base64_encode(user_data.str());

    // Forming the quote creation command that takes hash as an input
    std::ostringstream attest_cmd;
    attest_cmd << "attest -inform base64 -in " << encoded_user_data << " -out quote.dat";
    std::string attest_cmd_with_hash = attest_cmd.str();
    //cout << attest_cmd_with_hash << endl;
    uint8_t ret_code = system(attest_cmd_with_hash.c_str());

    if (ret_code != 0) {
        cout << "attest command execution failed or returned "
        "non-zero: " << ret_code << endl;
        return(ret);
    }

    // Removing extra padding to decrease size of quote data
    const char* sed_cmd = "sed \"$ s/\\x00*$//\" quote.dat > truncated_quote.dat";
    uint8_t status = system(sed_cmd);
    std::vector<std::string> fileArray = {"quote.dat"};
    deleteFiles(fileArray);

    if (status != 0) {
        std::cerr << "Error executing sed command." << std::endl;
	return(ret);
    }

    // Open the .dat file in binary mode
    std::ifstream file("truncated_quote.dat", std::ios::binary);

    // Check if the file is opened successfully
    if (!file.is_open()) {
        std::cerr << "Error opening file" << std::endl;
        return(ret) ;
    }

    // Seek to the end of the file to determine its size
    file.seekg(0, std::ios::end);
    std::streampos fileSize = file.tellg();
    file.seekg(0, std::ios::beg);

    // Create a vector to hold the data
    std::vector<unsigned char> data(fileSize);

    // Read the data from the file into the vector
    file.read(reinterpret_cast<char*>(data.data()), fileSize);

    // Check if the read operation was successful
    if (!file) {
        std::cerr << "Error reading file" << std::endl;
        return(ret);
    }

    // Close the file
    file.close();
    fileArray = {"truncated_quote.dat"};
    deleteFiles(fileArray);

    std::vector<unsigned char> user_data_bytes = Utils::base64url_to_binary(encoded_user_data);

    quote_size = data.size();
    // claims_size is size of hex string representation of 32 byte hash
    uint32_t claims_size = SHA256_DIGEST_LENGTH * 2;
    *quote_buf = (uint8_t *)realloc(*quote_buf, quote_size + claims_size + 8);
    memcpy(*quote_buf, (uint8_t *)&quote_size, 4);
    memcpy(*quote_buf + 4, (uint8_t *)&claims_size, 4);
    memcpy(*quote_buf + 8, (uint8_t *)data.data(), quote_size);
    memcpy(*quote_buf + 8 + quote_size, (uint8_t *)user_data_bytes.data(), claims_size);
    quote_size += claims_size + 8;

    cout << "Info: Generated TDX quote and claims data.\n" << endl;
    //print_hex_dump("\nInfo: Generated TDX quote and claims data\n", " ", *quote_buf, quote_size);

    ret = 1; // success
  }
  catch (std::exception &e) {
    cout << "Exception occured. Details - " << e.what() << endl;
    return(ret);
  }

  return(ret);
};
#endif // SGX_RA_TLS_GCP_TDX_BACKEND

#ifdef SGX_RA_TLS_TDX_BACKEND
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

    ret = parse_quote(x509, &quote_buf, quote_size);
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
#endif // SGX_RA_TLS_TDX_BACKEND

std::vector<std::string> tdx_generate_key_cert() {
    return generate_key_cert(tdx_generate_quote);
}

} // namespace sgx
} // namespace grpc

#endif // SGX_RA_TLS_TDX_BACKEND || SGX_RA_TLS_AZURE_TDX_BACKEND
