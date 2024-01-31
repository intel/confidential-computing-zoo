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

#if defined(SGX_RA_TLS_TDX_BACKEND)

#include <grpcpp/security/sgx/sgx_ra_tls_backends.h>
#include <grpcpp/security/sgx/sgx_ra_tls_impl.h>

#include <stdio.h>
#include <vector>
#include <string>
#include <assert.h>
#include <fstream>
#include <cstring>

#include "sgx_urts.h"
#include "sgx_quote_4.h"

namespace grpc {
namespace sgx {

#include <sgx_ql_quote.h>
#include <sgx_dcap_quoteverify.h>
#include <tdx_attest.h>

/*
// https://github.com/intel/SGXDataCenterAttestationPrimitives/blob/tdx_1.5_dcap_mvp_23q1/QuoteGeneration/quote_wrapper/common/inc/sgx_quote_4.h
typedef struct _sgx_quote4_t {
    sgx_quote4_header_t header;
    sgx_report2_body_t report_body;
    uint32_t signature_data_len;
    uint8_t signature_data[];
} sgx_quote4_t;

typedef struct sgx_report2_body_t {
    tee_report_data_t report_data;
    ...
}

typedef struct _tdx_report_data_t
{
    uint8_t d[TDX_REPORT_DATA_SIZE];
} tdx_report_data_t;

typedef struct _tdx_report_t
{
    uint8_t d[TDX_REPORT_SIZE];
} tdx_report_t;

// https://github.com/intel/linux-sgx/blob/tdx_1.5_mvp_23q1/common/inc/sgx_report2.h#L59
struct tee_report_data_t {
    uint8_t d[SGX_REPORT2_DATA_SIZE];
}
*/

const uint8_t g_att_key_id_list[256] = {0};

typedef struct _hash_t {
    uint8_t d[SHA256_DIGEST_LENGTH];
    size_t size;
} hash_t;

static void tdx_gen_report_data(uint8_t *reportdata, uint8_t *hash) {
    hash_t h = {{0}, 0};
    h.size = sizeof(hash);
    memcpy(h.d, hash, h.size);
    memcpy(reportdata, &h, sizeof(h));
    // printf("write hash %s, size: %lu\n", byte_to_hex((const char*)h.d, h.size).c_str(), h.size);
}

static int tdx_generate_quote(
        uint8_t **quote_buf, uint32_t &quote_size, uint8_t *hash) {
    int ret = -1;

    tdx_uuid_t selected_att_key_id = {0};
    tdx_report_data_t report_data = {{0}};
    tdx_report_t tdx_report = {{0}};

    tdx_gen_report_data(report_data.d, hash);
    // print_hex_dump("TDX report data\n", " ", report_data.d, sizeof(report_data.d));

    if (TDX_ATTEST_SUCCESS != tdx_att_get_report(&report_data, &tdx_report)) {
        grpc_fprintf(stderr, "failed to get the report.\n");
        ret = 0;
    }
    // print_hex_dump("TDX report\n", " ", tdx_report.d, sizeof(tdx_report.d));

    // https://github.com/intel/SGXDataCenterAttestationPrimitives/blob/dcap_1.15_reproducible/QuoteGeneration/quote_wrapper/tdx_attest/tdx_attest.c#L179
    if (TDX_ATTEST_SUCCESS != tdx_att_get_quote(&report_data, NULL, 0, &selected_att_key_id,
        quote_buf, &quote_size, 0)) {
        grpc_fprintf(stderr, "failed to get the quote.\n");
        ret = 0;
    }
    // print_hex_dump("TDX quote data\n ", *quote_buf, quote_size);
    return ret;
};

std::vector<std::string> tdx_generate_key_cert() {
    return generate_key_cert(tdx_generate_quote);
}

int tdx_parse_quote(X509 *x509, uint8_t **quote, uint32_t &quote_size) {
    return parse_quote(x509, quote, quote_size);
};

sgx_report2_body_t * tdx_parse_report_body(void *quote_buf) {
    return &((sgx_quote4_t *)quote_buf)->report_body;
}

ra_tls_measurement tdx_parse_measurement(const char *der_crt, size_t len) {
    return ra_tls_measurement();
}

void tdx_verify_init() {
    generate_key_cert(dummy_generate_quote);
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
    // https://github.com/intel/SGXDataCenterAttestationPrimitives/blob/dcap_1.15_reproducible/QuoteVerification/dcap_quoteverify/sgx_dcap_quoteverify.cpp#L777
    // print_hex_dump("TDX parse quote data\n", " ", quote_buf, quote_size);
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
    sgx_report2_body_t *report_body = nullptr;
    hash_t hash = {{0}, 0};

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

    ret = tdx_verify_quote(quote_buf, quote_size);
    if (ret != 0) {
        grpc_printf("verify quote failed.\n");
        goto out;
    }

    report_body = tdx_parse_report_body(quote_buf);
    memcpy(&hash, report_body->report_data.d, sizeof(hash));
    ret = verify_pubkey_hash(x509, hash.d, hash.size);
    if (ret != 0) {
        grpc_printf("verify the public key hash failed.\n");
        goto out;
    }

    ret = verify_measurement(
            (const char*)report_body->mr_seam.m,
            (const char*)report_body->mrsigner_seam.m,
            (const char*)report_body->mr_td.m,
            (const char*)report_body->mr_config_id.m,
            (const char*)report_body->mr_owner.m,
            (const char*)report_body->mr_owner_config.m,
            (const char*)report_body->rt_mr[0].m,
            (const char*)report_body->rt_mr[1].m,
            (const char*)report_body->rt_mr[2].m,
            (const char*)report_body->rt_mr[3].m);

out:
    BIO_free(bio);
    return ret;
}

} // namespace sgx
} // namespace grpc

#endif // SGX_RA_TLS_TDX_BACKEND
