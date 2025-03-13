#include <stdio.h>
#include <vector>
#include <string>
#include <assert.h>
#include <fstream>

#include <cstring>

#include "sgx_ql_quote.h"
#include "sgx_dcap_quoteverify.h"

#include <iostream>
#include <stdexcept>
#include <ctime>
#include <openssl/ssl.h>
#include <openssl/bio.h>
#include <openssl/evp.h>

#include "httplib.h"
#include <nlohmann/json.hpp>

using namespace httplib;
using namespace std;

namespace nlohmann {
    template <>
    struct adl_serializer<std::vector<uint8_t>> {
        static void to_json(json& j, const std::vector<uint8_t>& data) {
            j = json::binary(data);
        }
        static void from_json(const json& j, std::vector<uint8_t>& data) {
            data = j.get_binary();
        }
    };
}
using json = nlohmann::json;
#define log(msg, ...)                             \
    do                                            \
    {                                             \
        printf("[APP] " msg "\n", ##__VA_ARGS__); \
        fflush(stdout);                           \
    } while (0)

typedef union _supp_ver_t
{
    uint32_t version;
    struct
    {
        uint16_t major_version;
        uint16_t minor_version;
    };
} supp_ver_t;

void print_hex(const std::vector<uint8_t>& data) {
    for (uint8_t byte : data) {
        printf("%02x ", byte);  // 两位十六进制，空格分隔
    }
    printf("\n");
}

std::vector<uint8_t> base64_decode(const std::string& encoded) {
    BIO* b64 = BIO_new(BIO_f_base64());
    BIO* mem = BIO_new_mem_buf(encoded.c_str(), encoded.length());
    BIO_push(b64, mem);
    BIO_set_flags(b64, BIO_FLAGS_BASE64_NO_NL);

    std::vector<uint8_t> decoded(encoded.length());
    int len = BIO_read(b64, decoded.data(), encoded.length());
    if (len < 0) {
        BIO_free_all(b64);
        throw std::runtime_error("Base64 decoding failed");
    }
    decoded.resize(len);
    BIO_free_all(b64);
    return decoded;
}

vector<uint8_t> readBinaryContent(const string &filePath)
{
    ifstream file(filePath, ios::binary);
    if (!file.is_open())
    {
        log("Error: Unable to open quote file %s", filePath.c_str());
        return {};
    }

    file.seekg(0, ios_base::end);
    streampos fileSize = file.tellg();

    file.seekg(0, ios_base::beg);
    vector<uint8_t> retVal(fileSize);
    file.read(reinterpret_cast<char *>(retVal.data()), fileSize);
    file.close();
    return retVal;
}
#define PATHSIZE 0x418U

/**
 * @param quote - ECDSA quote buffer
 * @param use_qve - Set quote verification mode
 *                   If true, quote verification will be performed by Intel QvE
 *                   If false, quote verification will be performed by untrusted QVL
 */
int handle_quote_verification(vector<uint8_t> quote, bool use_qve)
{
    (void)use_qve;

    int ret = 0;
    time_t current_time = 0;
    quote3_error_t dcap_ret = SGX_QL_ERROR_UNEXPECTED;
    uint32_t collateral_expiration_status = 1;
    sgx_ql_qv_result_t quote_verification_result = SGX_QL_QV_RESULT_UNSPECIFIED;
    

    tee_supp_data_descriptor_t supp_data;

    // You can also set specify a major version in this structure, then we will always return supplemental data of the major version
    // set major verison to 0 means always return latest supplemental data
    memset(&supp_data, 0, sizeof(tee_supp_data_descriptor_t));

    supp_ver_t latest_ver;


    {
        // call DCAP quote verify library to get supplemental latest version and data size
        // version is a combination of major_version and minor version
        // you can set the major version in 'supp_data.major_version' to get old version supplemental data
        // only support major_version 3 right now
        dcap_ret = tee_get_supplemental_data_version_and_size(quote.data(),
                                                              (uint32_t)quote.size(),
                                                              &latest_ver.version,
                                                              &supp_data.data_size);

        if (dcap_ret == SGX_QL_SUCCESS  && supp_data.data_size == sizeof(sgx_ql_qv_supplemental_t))
        {
            log("Info: tee_get_quote_supplemental_data_version_and_size successfully returned.");
            log("Info: latest supplemental data major version: %d, minor version: %d, size: %d", latest_ver.major_version, latest_ver.minor_version, supp_data.data_size);
            supp_data.p_data = (uint8_t *)malloc(supp_data.data_size);
            if (supp_data.p_data != NULL)
            {
                memset(supp_data.p_data, 0, supp_data.data_size);
            }

            // Just print error in sample
            //
            else
            {
                log("Error: Cannot allocate memory for supplemental data.");
                supp_data.data_size = 0;
            }
        }
        else
        {
            if (dcap_ret != SGX_QL_SUCCESS )
                log("Error: tee_get_quote_supplemental_data_size failed: 0x%04x", dcap_ret);

            if (supp_data.data_size != sizeof(sgx_ql_qv_supplemental_t))
                log("Warning: Quote supplemental data size is different between DCAP QVL and QvE, please make sure you installed DCAP QVL and QvE from same release.");

            supp_data.data_size = 0;
        }

        // set current time. This is only for sample purposes, in production mode a trusted time should be used.
        //
        current_time = time(NULL);

        // call DCAP quote verify library for quote verification
        // here you can choose 'trusted' or 'untrusted' quote verification by specifying parameter '&qve_report_info'
        // if '&qve_report_info' is NOT NULL, this API will call Intel QvE to verify quote
        // if '&qve_report_info' is NULL, this API will call 'untrusted quote verify lib' to verify quote, this mode doesn't rely on SGX capable system, but the results can not be cryptographically authenticated
        dcap_ret = tee_verify_quote(
            quote.data(), (uint32_t)quote.size(),
            NULL,
            current_time,
            &collateral_expiration_status,
            &quote_verification_result,
            NULL,
            &supp_data);
        if (dcap_ret == SGX_QL_SUCCESS )
        {
            log("Info: App: tee_verify_quote successfully returned.");
        }
        else
        {
            log("Error: App: tee_verify_quote failed: 0x%04x", dcap_ret);
            goto cleanup;
        }

        // check verification result
        //
        switch (quote_verification_result)
        {
        case SGX_QL_QV_RESULT_OK:
            // check verification collateral expiration status
            // this value should be considered in your own attestation/verification policy
            //
            if (collateral_expiration_status == 0)
            {
                log("Info: App: Verification completed successfully.");
                ret = 0;
            }
            else
            {
                log("Warning: App: Verification completed, but collateral is out of date based on 'expiration_check_date' you provided.");
                ret = 1;
            }
            break;
        case SGX_QL_QV_RESULT_CONFIG_NEEDED:
        case SGX_QL_QV_RESULT_OUT_OF_DATE:
        case SGX_QL_QV_RESULT_OUT_OF_DATE_CONFIG_NEEDED:
        case SGX_QL_QV_RESULT_SW_HARDENING_NEEDED:
        case SGX_QL_QV_RESULT_CONFIG_AND_SW_HARDENING_NEEDED:
            log("Warning: App: Verification completed with Non-terminal result: %x", quote_verification_result);
            ret = 1;
            break;
        case SGX_QL_QV_RESULT_INVALID_SIGNATURE:
        case SGX_QL_QV_RESULT_REVOKED:
        case SGX_QL_QV_RESULT_UNSPECIFIED:
        default:
            log("Error: App: Verification completed with Terminal result: %x", quote_verification_result);
            ret = -1;
            break;
        }

        // check supplemental data if necessary
        //
        if (dcap_ret == SGX_QL_SUCCESS  && supp_data.p_data != NULL && supp_data.data_size > 0)
        {
            sgx_ql_qv_supplemental_t *p = (sgx_ql_qv_supplemental_t *)supp_data.p_data;

            // you can check supplemental data based on your own attestation/verification policy
            // here we only print supplemental data version for demo usage
            //
            log("Info: Supplemental data Major Version: %d", p->major_version);
            log("Info: Supplemental data Minor Version: %d", p->minor_version);

            // print SA list if exist, SA list is supported from version 3.1
            //
            if (p->version > 3 && strlen(p->sa_list) > 0)
            {
                log("Info: Advisory ID: %s", p->sa_list);
            }
        }
    }

cleanup:
    if (supp_data.p_data != NULL)
    {
        free(supp_data.p_data);
    }

    return ret;
}

std::vector<uint8_t> hex_string_to_bytes(const std::string& hex_str) {
    std::vector<uint8_t> bytes;
    std::istringstream iss(hex_str);
    std::string byte_str;

    while (iss >> byte_str) {
        if (byte_str.length() != 2) {
            throw std::invalid_argument("Invalid hex byte format: " + byte_str);
        }

        try {
            auto byte = static_cast<uint8_t>(std::stoul(byte_str, nullptr, 16));
            bytes.push_back(byte);
        } catch (...) {
            throw std::invalid_argument("Conversion failed for: " + byte_str);
        }
    }

    return bytes;
}


/**
 * @param Request - remote request message
 * @param Response - response message
 *                   If TDX Quote verified pass, send SUCCESS;
 *                   If TDX Quote verified pass, send FAILED;
 */
void handle_tdx_attestation(const Request& req, Response& res)
{
    vector<uint8_t> raw_quote;

    std::cout << "------> Handle_tdx_attestation " << std::endl;
    std::cout << "---------> This Session Start <----------" << std::endl;
    try {
        // Parse request message
        // if Quote data read in base64 mode, decode it. 
        auto json_data = json::parse(req.body);
        std::string base64_quote = json_data["raw_quote_data"];
        //std::cout << "---------> raw_quote_data:" << base64_quote << std::endl;
        //raw_quote = base64_decode(base64_quote);
        raw_quote = hex_string_to_bytes(base64_quote);
        //std::cout << "---------> raw_quote_data:" << raw_quote << std::endl
        bool is_valid=0;
        //std::cout << "---------> Start to Print raw Quote     " << std::endl;
        //print_hex(raw_quote);
        //std::cout << "---------> End                      " << std::endl;
 
        // Call Quote Verification API         
        log("Quote verification:");
        if (handle_quote_verification(raw_quote, false) != 0)
        {
            std::cout << "---------> TDX Quote Verification Pass! " << std::endl;
            is_valid = 1;
        }else {
            std::cout << "---------> TDX Quote Verification Fail! " << std::endl;
            is_valid = 0;
        }
        
        // Response data format
        json response = {
            {"attestation_result", is_valid ? "SUCCESS" : "FAILED"},
            {"timestamp", static_cast<uint32_t>(time(nullptr))}
        };

        std::cout << "---------> Fill response with attest result  " << std::endl;
	res.set_header("Access-Control-Allow-Origin", "*");
        res.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
        res.set_header("Access-Control-Allow-Headers", "Content-Type");
        res.set_header("Access-Control-Max-Age", "86400");
        res.set_content(response.dump(), "application/json");

        std::cout << "---------> This Session End <----------" << std::endl;

    } catch (const json::exception& e) {
        res.status = 400;
        res.set_content(json{{"error", "JSON_PARSE_ERROR"}, {"message", e.what()}}.dump(), "application/json");
    } catch (const std::exception& e) {
        res.status = 500;
        res.set_content(json{{"error", "TDX_VALIDATION_ERROR"}, {"message", e.what()}}.dump(), "application/json");
    }

}

int main()
{
    httplib::Server svr;
    //SSLServer svr;
    svr.Options("/tdx_attest", [](const httplib::Request &req, httplib::Response &res) {

    res.set_header("Access-Control-Allow-Origin", "*"); 
    res.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
    res.set_header("Access-Control-Allow-Headers", "Content-Type");
    res.set_header("Access-Control-Max-Age", "86400"); 
    res.status = 200; 
    });

    svr.Post("/tdx_attest", handle_tdx_attestation);
    
    svr.set_read_timeout(10);
    svr.set_write_timeout(10);

    std::cout << "Starting TDX Attestation Service on port 8443..." << std::endl;
    svr.listen("0.0.0.0", 8443);
}
