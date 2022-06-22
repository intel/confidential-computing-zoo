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

#ifdef SGX_RA_TLS_OCCLUM_BACKEND

#include "sgx_ra_tls_backends.h"
#include "sgx_ra_tls_impl.h"

#ifdef SGX_RA_TLS_LIBRATS_SDK
#include "librats/api.h"
#endif

namespace grpc {
namespace sgx {

#include "sgx_quote_3.h"
#include "dcap_quote.h"

int occlum_generate_quote(
        uint8_t **quote_buf, uint32_t &quote_size, uint8_t *hash) {
#ifdef SGX_RA_TLS_LIBRATS_SDK
    int ret = 0;
    rats_conf_t conf;
    rats_attester_err_t aerr;
    attestation_evidence_t ev;
    rats_err_t err;

    if (!_ctx_.init_lib.get_handle()) {
	    _ctx_.init_lib.open("librats_lib.so", RTLD_GLOBAL | RTLD_NOW);
    }
    auto librats_init =
	    reinterpret_cast< rats_err_t (*)(rats_conf_t *conf, rats_core_context_t *ctx)>(
			    _ctx_.init_lib.get_func("librats_init"));

    if (!_ctx_.attest_lib.get_handle()) {
	    _ctx_.attest_lib.open("libattester_sgx_ecdsa.so", RTLD_GLOBAL | RTLD_NOW);
    }
    auto librats_collect_evidence =
	    reinterpret_cast< rats_attester_err_t (*)(rats_attester_ctx_t *ctx,
			    attestation_evidence_t *evidence, uint8_t *hash,
			    uint32_t hash_len)>(
				    _ctx_.attest_lib.get_func("librats_collect_evidence"));

    if (!_ctx_.cleanup_lib.get_handle()) {
	    _ctx_.cleanup_lib.open("librats_lib.so", RTLD_GLOBAL | RTLD_NOW);
    }
    auto librats_cleanup =
	    reinterpret_cast< rats_err_t (*)(rats_core_context_t *ctx)>(
			    _ctx_.cleanup_lib.get_func("librats_cleanup"));

    conf.api_version = RATS_API_VERSION_DEFAULT;
    conf.log_level = RATS_LOG_LEVEL_DEFAULT;
    memcpy(conf.attester_type, "sgx_ecdsa", sizeof(conf.attester_type));
    memcpy(conf.verifier_type, "sgx_ecdsa", sizeof(conf.verifier_type));

    rats_core_context_t *ctx = (rats_core_context_t *)malloc(sizeof(struct rats_core_context));
    if (!ctx) {
	    grpc_printf("couldn't allocate rats_core_context\n");
	    ret = -1;
    }
    memcpy(ev.type, "sgx_ecdsa", sizeof(ev.type));

    err = (*librats_init)(&conf, ctx);
    if (err != RATS_ERR_NONE) {
	    grpc_printf("librats initialization failed\n");
	    ret = -1;
    }

    aerr = (*librats_collect_evidence)(ctx->attester, &ev, (unsigned char *)hash, SHA256_DIGEST_LENGTH);
    if (aerr != RATS_ATTESTER_ERR_NONE) {
	    grpc_printf("librats collect evidence failed\n");
	    ret = -1;
    }

    quote_size = ev.ecdsa.quote_len;
    *quote_buf = (uint8_t*)calloc(quote_size, sizeof(uint8_t));
    if (nullptr == *quote_buf) {
	    grpc_printf("Couldn't allocate quote_buf\n");
    }
    memcpy(*quote_buf, ev.ecdsa.quote, quote_size);

    err = (*librats_cleanup)(ctx);
    if (err != RATS_ERR_NONE) {
	    grpc_printf("librats cleanup failed\n");
	    ret = -1;
    }
#else
    void *handle = dcap_quote_open();
    quote_size = dcap_get_quote_size(handle);
    *quote_buf = (uint8_t*)calloc(quote_size, sizeof(uint8_t));
    if (nullptr == quote_buf) {
        grpc_printf("Couldn't allocate quote_buf\n");
    }

    sgx_report_data_t report_data = { 0 };
    memcpy(report_data.d, hash, SHA256_DIGEST_LENGTH);

    int ret = dcap_generate_quote(handle, *quote_buf, &report_data);
    if (ret != 0) {
        grpc_printf("Error in dcap_generate_quote.\n");
    }

    dcap_quote_close(handle);
#endif

    return !ret;
};

std::vector<std::string> occlum_generate_key_cert() {
    return generate_key_cert(occlum_generate_quote);
}

int occlum_parse_quote(X509 *x509, uint8_t **quote, uint32_t &quote_size) {
    return parse_quote(x509, quote, quote_size);
};

void occlum_verify_init() {
    generate_key_cert(dummy_generate_quote);
};

int occlum_verify_quote(uint8_t *quote_buf, size_t quote_size) {
    void *handle = dcap_quote_open();

    uint32_t supplemental_size = dcap_get_supplemental_data_size(handle);
    uint8_t *p_supplemental_buffer = (uint8_t *)calloc(supplemental_size, sizeof(uint8_t));
    if (NULL == p_supplemental_buffer) {
        grpc_printf("Couldn't allocate supplemental buffer\n");
    }

    sgx_ql_qv_result_t quote_verification_result = SGX_QL_QV_RESULT_UNSPECIFIED;
    uint32_t collateral_expiration_status = 1;
    uint32_t ret = dcap_verify_quote(
        handle,
        quote_buf,
        quote_size,
        &collateral_expiration_status,
        &quote_verification_result,
        supplemental_size,
        p_supplemental_buffer);

    if (ret != 0) {
        grpc_printf( "Error in dcap_verify_quote.\n");
    }

    if (collateral_expiration_status != 0) {
        grpc_printf("The verification collateral has expired!\n");
    }

    switch (quote_verification_result) {
        case SGX_QL_QV_RESULT_OK:
            grpc_printf("Succeed to verify the quote!\n");
            break;
        case SGX_QL_QV_RESULT_CONFIG_NEEDED:
        case SGX_QL_QV_RESULT_OUT_OF_DATE:
        case SGX_QL_QV_RESULT_OUT_OF_DATE_CONFIG_NEEDED:
        case SGX_QL_QV_RESULT_SW_HARDENING_NEEDED:
        case SGX_QL_QV_RESULT_CONFIG_AND_SW_HARDENING_NEEDED:
            grpc_printf("WARN: App: Verification completed with Non-terminal result: %x\n",
                   quote_verification_result);
            break;
        case SGX_QL_QV_RESULT_INVALID_SIGNATURE:
        case SGX_QL_QV_RESULT_REVOKED:
        case SGX_QL_QV_RESULT_UNSPECIFIED:
        default:
            grpc_printf("\tError: App: Verification completed with Terminal result: %x\n",
                   quote_verification_result);
    }
    check_free(p_supplemental_buffer);
    dcap_quote_close(handle);
    return ret;
}

uint8_t *occlum_parse_pubkey_hash(void *p_quote) {
    auto p_rep_body =
        (sgx_report_body_t *)(&((sgx_quote3_t *)p_quote)->report_body);
    auto p_rep_data = (sgx_report_data_t *)(&p_rep_body->report_data);
    return p_rep_data->d;
}

sgx_report_body_t * occlum_parse_report_body(void *p_quote) {
    return (sgx_report_body_t *)(&((sgx_quote3_t *)p_quote)->report_body);
}

int occlum_verify_cert(const char *der_crt, size_t len) {
    int ret = 0;
    uint32_t quote_size = 0;
    uint8_t *quote_buf = nullptr;
    uint8_t *pubkey_hash = nullptr;
    sgx_report_body_t *p_rep_body = nullptr;

#ifdef SGX_RA_TLS_LIBRATS_SDK
    rats_conf_t conf;
    rats_verifier_err_t verr;
    attestation_evidence_t ev;
    rats_err_t err;
    rats_core_context_t *ctx;

    if (!_ctx_.init_lib.get_handle()) {
	    _ctx_.init_lib.open("librats_lib.so", RTLD_LAZY);
    }
    auto librats_init =
	    reinterpret_cast< rats_err_t (*)(rats_conf_t *conf, rats_core_context_t *ctx)>(
			    _ctx_.init_lib.get_func("librats_init"));

    if (!_ctx_.verify_lib.get_handle()) {
	    _ctx_.verify_lib.open("libverifier_sgx_ecdsa.so", RTLD_LAZY);
    }
    auto librats_verify_evidence =
	    reinterpret_cast< rats_verifier_err_t (*)(rats_verifier_ctx_t *ctx,
			    attestation_evidence_t *evidence, uint8_t *hash,
			    uint32_t hash_len)>(
				    _ctx_.verify_lib.get_func("librats_verify_evidence"));

    if (!_ctx_.cleanup_lib.get_handle()) {
	    _ctx_.cleanup_lib.open("librats_lib.so", RTLD_GLOBAL | RTLD_NOW);//RTLD_LAZY);
    }
    auto librats_cleanup =
	    reinterpret_cast< rats_err_t (*)(rats_core_context_t *ctx)>(
			    _ctx_.cleanup_lib.get_func("librats_cleanup"));
#endif
    BIO *bio = BIO_new(BIO_s_mem());
    BIO_write(bio, der_crt, len);
    X509 *x509 = PEM_read_bio_X509(bio, NULL, NULL, NULL);
    if (!x509) {
        grpc_printf("parse crt failed!\n");
        ret = -1;
        goto out;
    }

    ret = occlum_parse_quote(x509, &quote_buf, quote_size);
    if (ret != 0) {
        grpc_printf("parse quote failed!\n");
        goto out;
    }

#ifdef SGX_RA_TLS_LIBRATS_SDK
    conf.api_version = RATS_API_VERSION_DEFAULT;
    conf.log_level = RATS_LOG_LEVEL_DEFAULT;
    memcpy(conf.verifier_type, "sgx_ecdsa", sizeof(conf.verifier_type));
    memcpy(conf.attester_type, "sgx_ecdsa", sizeof(conf.attester_type));

    ctx = (rats_core_context_t *)malloc(sizeof(struct rats_core_context));
    if (!ctx) {
	    grpc_printf("couldn't malloc rats_core_context\n");
	    ret = -1;
	    goto out;
    }
    memcpy(ev.type, "sgx_ecdsa", sizeof(ev.type));
    memcpy(ev.ecdsa.quote, quote_buf, quote_size);
    ev.ecdsa.quote_len = quote_size;

    err = (*librats_init)(&conf, ctx);
    if (err != RATS_ERR_NONE) {
	    grpc_printf("librats initialization failed\n");
	    ret = -1;
	    goto out;
    }

    pubkey_hash = occlum_parse_pubkey_hash(quote_buf);
    verr = (*librats_verify_evidence)(ctx->verifier, &ev, pubkey_hash, SHA256_DIGEST_LENGTH);
    if (verr != RATS_VERIFIER_ERR_NONE) {
	    grpc_printf("librats verify evidence failed\n");
	    ret = -1;
	    goto out;
    }

    err = (*librats_cleanup)(ctx);
    if (err != RATS_ERR_NONE) {
	    grpc_printf("librats cleanup failed\n");
	    ret = -1;
    }
#else
    ret = occlum_verify_quote(quote_buf, quote_size);
    if (ret != 0) {
        grpc_printf("verify quote failed!\n");
        goto out;
    }

    pubkey_hash = occlum_parse_pubkey_hash(quote_buf);
    ret = verify_pubkey_hash(x509, pubkey_hash, SHA256_DIGEST_LENGTH);
    if (ret != 0) {
        grpc_printf("verify pubkey hash failed!\n");
        goto out;
    }
#endif

    p_rep_body = occlum_parse_report_body(quote_buf);
    ret = verify_measurement((const char *)&p_rep_body->mr_enclave,
                             (const char *)&p_rep_body->mr_signer,
                             (const char *)&p_rep_body->isv_prod_id,
                             (const char *)&p_rep_body->isv_svn); 

out:
    BIO_free(bio);
    return ret;
}

ra_tls_measurement occlum_parse_measurement(const char *der_crt, size_t len) {
    int ret = 0;
    uint32_t quote_size = 0;
    uint8_t *quote_buf = nullptr;
    uint8_t *pubkey_hash = nullptr;
    sgx_report_body_t *p_rep_body = nullptr;
    struct ra_tls_measurement mrs;

    BIO *bio = BIO_new(BIO_s_mem());
    BIO_write(bio, der_crt, len);
    X509 *x509 = PEM_read_bio_X509(bio, NULL, NULL, NULL);
    if (!x509) {
        grpc_printf("parse crt failed!\n");
        ret = -1;
        goto out;
    }

    ret = occlum_parse_quote(x509, &quote_buf, quote_size);
    if (ret != 0) {
        grpc_printf("parse quote failed!\n");
        goto out;
    }

    p_rep_body = occlum_parse_report_body(quote_buf);
    memcmp(mrs.mr_enclave, &p_rep_body->mr_enclave, 32);
    memcmp(mrs.mr_signer, &p_rep_body->mr_signer, 32);
    mrs.isv_prod_id = p_rep_body->isv_prod_id;
    mrs.isv_svn = p_rep_body->isv_svn;

out:
    BIO_free(bio);
    return mrs;
}

} // namespace sgx
} // namespace grpc

#endif // SGX_RA_TLS_OCCLUM_BACKEND
