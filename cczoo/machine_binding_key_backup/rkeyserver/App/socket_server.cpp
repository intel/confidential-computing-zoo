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

#include<stdio.h>
#include<string.h>
#include<stdlib.h>
#include<sys/socket.h>
#include<arpa/inet.h>
#include<unistd.h>
#include<errno.h>
#include<pthread.h>
#include<error.h>

#include "sgx_quote_3.h"
#include <sgx_uae_launch.h>
#include "sgx_urts.h"
#include "sgx_ql_quote.h"
#include "sgx_dcap_quoteverify.h"
#include "enclave_u.h"

#include "ecp.h"
#include "sample_libcrypto.h"
#include "socket_server.h"
#include "rand.h"
#include "CacheController.h"
#include "log_utils.h"

extern sgx_enclave_id_t g_enclave_id;

namespace socket_server {

// This is the private EC key of SP, the corresponding public EC key is
// hard coded in isv_enclave. It is based on NIST P-256 curve.
static const sample_ec256_private_t g_sp_priv_key = {
    {
        0x90, 0xe7, 0x6c, 0xbb, 0x2d, 0x52, 0xa1, 0xce,
        0x3b, 0x66, 0xde, 0x11, 0x43, 0x9c, 0x87, 0xec,
        0x1f, 0x86, 0x6a, 0x3b, 0x65, 0xb6, 0xae, 0xea,
        0xad, 0x57, 0x34, 0x53, 0xd1, 0x03, 0x8c, 0x01
    }
};

// This is the public EC key of SP, this key is hard coded in isv_enclave.
// It is based on NIST P-256 curve. Not used in the SP code.
static const sample_ec_pub_t g_sp_pub_key = {
    {
        0x72, 0x12, 0x8a, 0x7a, 0x17, 0x52, 0x6e, 0xbf,
        0x85, 0xd0, 0x3a, 0x62, 0x37, 0x30, 0xae, 0xad,
        0x3e, 0x3d, 0xaa, 0xee, 0x9c, 0x60, 0x73, 0x1d,
        0xb0, 0x5b, 0xe8, 0x62, 0x1c, 0x4b, 0xeb, 0x38
    },
    {
        0xd4, 0x81, 0x40, 0xd9, 0x50, 0xe2, 0x57, 0x7b,
        0x26, 0xee, 0xb7, 0x41, 0xe7, 0xc6, 0x14, 0xe2,
        0x24, 0xb7, 0xbd, 0xc9, 0x03, 0xf2, 0x9a, 0x28,
        0xa8, 0x3c, 0xc8, 0x10, 0x11, 0x14, 0x5e, 0x06
    }
};

sample_spid_t g_spid;

static char* hexToCharIP(struct in_addr addrIP)
{
    char* ip;
    unsigned int intIP;
    memcpy(&intIP, &addrIP,sizeof(unsigned int));
    int a = (intIP >> 24) & 0xFF;
    int b = (intIP >> 16) & 0xFF;
    int c = (intIP >> 8) & 0xFF;
    int d = intIP & 0xFF;
    if((ip = (char*)malloc(16*sizeof(char))) == NULL) {
        return NULL;
    }
    sprintf(ip, "%d.%d.%d.%d", d,c,b,a);
    return ip;
}

static bool RecvAll(int32_t sock, void *data, int32_t data_size)
{
    char *data_ptr = (char*) data;
    int32_t bytes_recv;

    while (data_size > 0)
    {
        bytes_recv = recv(sock, data_ptr, data_size, 0);
        if (bytes_recv == 0) {
            return true;
        }
        if (bytes_recv < 0) {
            printf("failed to read data\n");
            return false;
        }

        data_ptr += bytes_recv;
        data_size -= bytes_recv;
    }

    return true;
}

static bool SendAll(int32_t sock, const void *data, int32_t data_size)
{
    const char *data_ptr = (const char*) data;
    int32_t bytes_sent;

    while (data_size > 0)
    {
        bytes_sent = send(sock, data_ptr, data_size, 0);
        if (bytes_sent < 1)
            return false;

        data_ptr += bytes_sent;
        data_size -= bytes_sent;
    }

    return true;
}

static int32_t SendResponse(int32_t sockfd,
                ra_samp_response_header_t *resp) {
    uint32_t resp_size;
    uint32_t ret = NO_ERROR;

    resp_size = resp->size + sizeof(ra_samp_response_header_t);

    if (!SendAll(sockfd, &resp_size, sizeof(resp_size))) {
        printf("send resp_size failed\n");
        return ERR_IO;
    }
    if (!SendAll(sockfd, resp, resp_size)) {
        printf("send out_msg failed\n");
        return ERR_IO;
    }

    printf("send response success with msg type(%d)\n", resp->type);

    return ret;
}

static int32_t SendErrResponse(int32_t sockfd, int8_t type, int8_t err) {
    ra_samp_response_header_t  p_err_resp_full;
    memset(&p_err_resp_full, 0, sizeof(ra_samp_response_header_t));

    p_err_resp_full.type = type;
    p_err_resp_full.status[0] = err;
    return SendResponse(sockfd, &p_err_resp_full);
}


// call cachecontrol finalize session id
int sp_ra_proc_finalize_session_id_req(const sesion_id_t sessionId, ra_samp_response_header_t **pp_finalize_session_res)
{
    int ret = 0;
    ra_samp_response_header_t* p_finalize_response = nullptr;
    if(!pp_finalize_session_res ) {
        return -1;
    }

    do
    {
        p_finalize_response = (ra_samp_response_header_t*)malloc(sizeof(ra_samp_response_header_t));
        if(!p_finalize_response){
            fprintf(stderr, "\nError, out of memory in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        memset(p_finalize_response, 0, sizeof(ra_samp_response_header_t));
        // set response header
        p_finalize_response->type = TYPE_RA_FINALIZE_SESSION_ID_RES;
        ret = db_finalize(sessionId);
        if(ret!= NO_ERROR){
            fprintf(stderr, "\nError, failed in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
    }while(0);

    if(ret){
        *pp_finalize_session_res = NULL;
        SAFE_FREE(p_finalize_response);
    }
    else{
        // Freed by the network simulator in ra_free_network_response_buffer
        *pp_finalize_session_res = p_finalize_response;
    }
    return ret;

}


// get session id from cachecontroller
// if get session id ok then
// return session id to rkeycache
int sp_ra_proc_get_session_id_req(ra_samp_response_header_t **pp_session_res)
{
    int ret = 0;
    ra_samp_response_header_t* p_response = nullptr;
    sesion_id_t sessionId = {0};
    if(!pp_session_res) {
        return -1;
    }

    do
    {
        p_response = (ra_samp_response_header_t*)malloc(sizeof(ra_samp_response_header_t));
        if(!p_response){
            fprintf(stderr, "\nError, out of memory in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        memset(p_response, 0, sizeof(ra_samp_response_header_t));
        // set response header
        p_response->type = TYPE_RA_GET_SESSION_ID_RES;
        ret = db_initialize(sessionId);
        if(ret!= NO_ERROR || !sessionId){
            fprintf(stderr, "\nError, failed in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        memcpy_s(p_response->sessionId, SESSION_ID_SIZE, sessionId, SESSION_ID_SIZE);
    }while(0);

    if(ret){
        *pp_session_res = NULL;
        SAFE_FREE(p_response);
    }
    else{
        // Freed by the network simulator in ra_free_network_response_buffer
        *pp_session_res = p_response;
    }
    return ret;
}


// Verify message 1 then generate and return message 2 to isv.
int sp_ra_proc_msg1_req(const sample_ra_msg1_t *p_msg1,
                        uint32_t msg1_size,
                        sesion_id_t sessionId,
                        ra_samp_response_header_t **pp_msg2)
{
    int ret = 0;
    sp_db_item_t *sp_db = NULL;
    ra_samp_response_header_t* p_msg2_full = NULL;
    sample_ra_msg2_t *p_msg2 = NULL;
    sample_ecc_state_handle_t ecc_state = NULL;
    sample_status_t sample_ret = SAMPLE_SUCCESS;
    bool derive_ret = false;

    if(!p_msg1 || !pp_msg2 || (msg1_size != sizeof(sample_ra_msg1_t))) {
        return -1;
    }

    do
    {
        // Get the sig_rl from attestation server using GID.
        // GID is Base-16 encoded of EPID GID in little-endian format.
        // In the product, the SP and attestation server uses an established channel for
        // communication.
        uint8_t* sig_rl = NULL;
        uint32_t sig_rl_size = 0;

        // get sp_gb from cacheController
        int32_t controller_ret = get_session_db(sessionId, &sp_db);
        if(controller_ret != NO_ERROR){
            fprintf(stderr, "\nError, get session db in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        // Need to save the client's public ECDH key to local storage
        if (memcpy_s(&sp_db->g_a, sizeof(sp_db->g_a), &p_msg1->g_a,
                     sizeof(p_msg1->g_a)))
        {
            fprintf(stderr, "\nError, cannot do memcpy in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        // Generate the Service providers ECDH key pair.
        sample_ret = sample_ecc256_open_context(&ecc_state);
        if(SAMPLE_SUCCESS != sample_ret)
        {
            fprintf(stderr, "\nError, cannot get ECC context in [%s].",
                             __FUNCTION__);
            ret = -1;
            break;
        }

        sample_ec256_public_t pub_key = {{0},{0}};
        sample_ec256_private_t priv_key = {{0}};
        sample_ret = sample_ecc256_create_key_pair(&priv_key, &pub_key,
                                                   ecc_state);
        if(SAMPLE_SUCCESS != sample_ret)
        {
            fprintf(stderr, "\nError, cannot generate key pair in [%s].",
                    __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        // Need to save the SP ECDH key pair to local storage.
        if(memcpy_s(&sp_db->b, sizeof(sp_db->b), &priv_key, sizeof(priv_key)) != 0)
        {
            fprintf(stderr, "\nError, cannot do memcpy in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        if(memcpy_s(&sp_db->g_b, sizeof(sp_db->g_b), &pub_key, sizeof(pub_key)) != 0)
        {
            fprintf(stderr, "\nError, cannot do memcpy in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        // Generate the client/SP shared secret
        sample_ec_dh_shared_t dh_key = {{0}};
        sample_ret = sample_ecc256_compute_shared_dhkey(&priv_key,
            (sample_ec256_public_t *)&p_msg1->g_a,
            (sample_ec256_dh_shared_t *)&dh_key,
            ecc_state);
        if(SAMPLE_SUCCESS != sample_ret)
        {
            fprintf(stderr, "\nError, compute share key fail in [%s].",
                    __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

#ifdef SUPPLIED_KEY_DERIVATION

        // smk is only needed for msg2 generation.
        derive_ret = derive_key(&dh_key, SAMPLE_DERIVE_KEY_SMK_SK,
            &sp_db->smk_key, &sp_db->sk_key);
        if(derive_ret != true)
        {
            fprintf(stderr, "\nError, derive key fail in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        // The rest of the keys are the shared secrets for future communication.
        derive_ret = derive_key(&dh_key, SAMPLE_DERIVE_KEY_MK_VK,
            &sp_db->mk_key, &sp_db->vk_key);
        if(derive_ret != true)
        {
            fprintf(stderr, "\nError, derive key fail in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
#else
        // smk is only needed for msg2 generation.
        derive_ret = derive_key(&dh_key, SAMPLE_DERIVE_KEY_SMK,
                                &sp_db->smk_key);
        if(derive_ret != true)
        {
            fprintf(stderr, "\nError, derive key fail in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        // The rest of the keys are the shared secrets for future communication.
        derive_ret = derive_key(&dh_key, SAMPLE_DERIVE_KEY_MK,
                                &sp_db->mk_key);
        if(derive_ret != true)
        {
            fprintf(stderr, "\nError, derive key fail in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        derive_ret = derive_key(&dh_key, SAMPLE_DERIVE_KEY_SK,
                                &sp_db->sk_key);
        if(derive_ret != true)
        {
            fprintf(stderr, "\nError, derive key fail in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        derive_ret = derive_key(&dh_key, SAMPLE_DERIVE_KEY_VK,
                                &sp_db->vk_key);
        if(derive_ret != true)
        {
            fprintf(stderr, "\nError, derive key fail in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
#endif

        uint32_t msg2_size = (uint32_t)sizeof(sample_ra_msg2_t) + sig_rl_size;
        p_msg2_full = (ra_samp_response_header_t*)malloc(msg2_size
                      + sizeof(ra_samp_response_header_t));
        if(!p_msg2_full)
        {
            fprintf(stderr, "\nError, out of memory in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        memset(p_msg2_full, 0, msg2_size + sizeof(ra_samp_response_header_t));
        p_msg2_full->type = TYPE_RA_MSG2;
        p_msg2_full->size = msg2_size;
        // The simulated message2 always passes.  This would need to be set
        // accordingly in a real service provider implementation.
        p_msg2_full->status[0] = 0;
        p_msg2_full->status[1] = 0;
        p_msg2 = (sample_ra_msg2_t *)p_msg2_full->body;

        // Assemble MSG2
        if(memcpy_s(&p_msg2->g_b, sizeof(p_msg2->g_b), &sp_db->g_b,
                    sizeof(sp_db->g_b)) ||
           memcpy_s(&p_msg2->spid, sizeof(sample_spid_t),
                    &g_spid, sizeof(g_spid)))
        {
            fprintf(stderr,"\nError, memcpy failed in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        // The service provider is responsible for selecting the proper EPID
        // signature type and to understand the implications of the choice!
        p_msg2->quote_type = SAMPLE_QUOTE_LINKABLE_SIGNATURE;

#ifdef SUPPLIED_KEY_DERIVATION
//isv defined key derivation function id
#define ISV_KDF_ID 2
        p_msg2->kdf_id = ISV_KDF_ID;
#else
        p_msg2->kdf_id = SAMPLE_AES_CMAC_KDF_ID;
#endif
        // Create gb_ga
        sample_ec_pub_t gb_ga[2];
        if(memcpy_s(&gb_ga[0], sizeof(gb_ga[0]), &sp_db->g_b,
                    sizeof(sp_db->g_b))
           || memcpy_s(&gb_ga[1], sizeof(gb_ga[1]), &sp_db->g_a,
                       sizeof(sp_db->g_a)))
        {
            fprintf(stderr,"\nError, memcpy failed in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        // Sign gb_ga
        sample_ret = sample_ecdsa_sign((uint8_t *)&gb_ga, sizeof(gb_ga),
                        (sample_ec256_private_t *)&g_sp_priv_key,
                        (sample_ec256_signature_t *)&p_msg2->sign_gb_ga,
                        ecc_state);
        if(SAMPLE_SUCCESS != sample_ret)
        {
            fprintf(stderr, "\nError, sign ga_gb fail in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        // Generate the CMACsmk for gb||SPID||TYPE||KDF_ID||Sigsp(gb,ga)
        uint8_t mac[SAMPLE_EC_MAC_SIZE] = {0};
        uint32_t cmac_size = offsetof(sample_ra_msg2_t, mac);
        sample_ret = sample_rijndael128_cmac_msg(&sp_db->smk_key,
            (uint8_t *)&p_msg2->g_b, cmac_size, &mac);
        if(SAMPLE_SUCCESS != sample_ret)
        {
            fprintf(stderr, "\nError, cmac fail in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        if(memcpy_s(&p_msg2->mac, sizeof(p_msg2->mac), mac, sizeof(mac)))
        {
            fprintf(stderr,"\nError, memcpy failed in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        if(memcpy_s(&p_msg2->sig_rl[0], sig_rl_size, sig_rl, sig_rl_size))
        {
            fprintf(stderr,"\nError, memcpy failed in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        p_msg2->sig_rl_size = sig_rl_size;

    }while(0);

    if(ret)
    {
        *pp_msg2 = NULL;
        SAFE_FREE(p_msg2_full);
    }
    else
    {
        // Freed by the network simulator in ra_free_network_response_buffer
        *pp_msg2 = p_msg2_full;
    }

    if(ecc_state)
    {
        sample_ecc256_close_context(ecc_state);
    }

    return ret;
}


// Process remote attestation message 3
int sp_ra_proc_msg3_req(const sample_ra_msg3_t *p_msg3,
                        uint32_t msg3_size,
                        sesion_id_t sessionId,
                        ra_samp_response_header_t **pp_att_result_msg)
{
    int ret = 0;
    sp_db_item_t* sp_db = NULL;
    sample_status_t sample_ret = SAMPLE_SUCCESS;
    const uint8_t *p_msg3_cmaced = NULL;
    const sgx_quote3_t *p_quote = NULL;
    sample_sha_state_handle_t sha_handle = NULL;
    sample_report_data_t report_data = {0};
    sample_ra_att_result_msg_t *p_att_result_msg = NULL;
    ra_samp_response_header_t* p_att_result_msg_full = NULL;

    sgx_ql_auth_data_t *p_auth_data;
    sgx_ql_ecdsa_sig_data_t *p_sig_data;
    sgx_ql_certification_data_t *p_cert_data;

    time_t current_time = 0;
    uint32_t supplemental_data_size = 0;
    uint8_t *p_supplemental_data = NULL;

    quote3_error_t dcap_ret = SGX_QL_ERROR_UNEXPECTED;
    sgx_ql_qv_result_t quote_verification_result = SGX_QL_QV_RESULT_UNSPECIFIED;
    uint32_t collateral_expiration_status = 1;
    
    sgx_ql_qe_report_info_t qve_report_info;
    unsigned char rand_nonce[16] = "59jslk201fgjmm;";

    uint32_t quote_size=0;
    
    if((!p_msg3) ||
       (msg3_size < sizeof(sample_ra_msg3_t)) ||
       (!pp_att_result_msg))
    {
        return SP_INTERNAL_ERROR;
    }

    do
    {
        // get sp_gb from cacheController
        int32_t controller_ret = get_session_db(sessionId, &sp_db);
        if(controller_ret != NO_ERROR){
            fprintf(stderr, "\nError, get session db in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        // Compare g_a in message 3 with local g_a.
        ret = memcmp(&sp_db->g_a, &p_msg3->g_a, sizeof(sample_ec_pub_t));
        if(ret)
        {
            fprintf(stderr, "\nError, g_a is not same [%s].", __FUNCTION__);
            ret = SP_PROTOCOL_ERROR;
            break;
        }
        //Make sure that msg3_size is bigger than sample_mac_t.
        uint32_t mac_size = msg3_size - (uint32_t)sizeof(sample_mac_t);
        p_msg3_cmaced = reinterpret_cast<const uint8_t*>(p_msg3);
        p_msg3_cmaced += sizeof(sample_mac_t);

        // Verify the message mac using SMK
        sample_cmac_128bit_tag_t mac = {0};
        sample_ret = sample_rijndael128_cmac_msg(&sp_db->smk_key,
                                           p_msg3_cmaced,
                                           mac_size,
                                           &mac);
        if(SAMPLE_SUCCESS != sample_ret)
        {
            fprintf(stderr, "\nError, cmac fail in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        // In real implementation, should use a time safe version of memcmp here,
        // in order to avoid side channel attack.
        ret = memcmp(&p_msg3->mac, mac, sizeof(mac));
        if(ret)
        {
            fprintf(stderr, "\nError, verify cmac fail [%s].", __FUNCTION__);
            ret = SP_INTEGRITY_FAILED;
            break;
        }

        if(memcpy_s(&sp_db->ps_sec_prop, sizeof(sp_db->ps_sec_prop),
            &p_msg3->ps_sec_prop, sizeof(p_msg3->ps_sec_prop)))
        {
            fprintf(stderr,"\nError, memcpy failed in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        //p_quote = (const sample_quote_t*)p_msg3->quote;
        p_quote = (sgx_quote3_t*)p_msg3->quote;
        quote_size = msg3_size - (uint32_t)sizeof(sample_mac_t)- (uint32_t)sizeof(sample_ec_pub_t)-(uint32_t)sizeof(sample_ps_sec_prop_desc_t);
        p_sig_data = (sgx_ql_ecdsa_sig_data_t *)p_quote->signature_data;
        p_auth_data = (sgx_ql_auth_data_t*)p_sig_data->auth_certification_data;
        p_cert_data = (sgx_ql_certification_data_t *)((uint8_t *)p_auth_data + sizeof(*p_auth_data) + p_auth_data->size);

        printf("cert_key_type = 0x%x\n", p_cert_data->cert_key_type);

        // Check the quote version if needed. Only check the Quote.version field if the enclave
        // identity fields have changed or the size of the quote has changed.  The version may
        // change without affecting the legacy fields or size of the quote structure.
        //if(p_quote->version < ACCEPTED_QUOTE_VERSION)
        //{
        //    fprintf(stderr,"\nError, quote version is too old.", __FUNCTION__);
        //    ret = SP_QUOTE_VERSION_ERROR;
        //    break;
        //}

        // Verify the report_data in the Quote matches the expected value.
        // The first 32 bytes of report_data are SHA256 HASH of {ga|gb|vk}.
        // The second 32 bytes of report_data are set to zero.
        sample_ret = sample_sha256_init(&sha_handle);
        if(sample_ret != SAMPLE_SUCCESS)
        {
            fprintf(stderr,"\nError, init hash failed in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        sample_ret = sample_sha256_update((uint8_t *)&(sp_db->g_a),
                                     sizeof(sp_db->g_a), sha_handle);
        if(sample_ret != SAMPLE_SUCCESS)
        {
            fprintf(stderr,"\nError, udpate hash failed in [%s].",
                    __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        sample_ret = sample_sha256_update((uint8_t *)&(sp_db->g_b),
                                     sizeof(sp_db->g_b), sha_handle);
        if(sample_ret != SAMPLE_SUCCESS)
        {
            fprintf(stderr,"\nError, udpate hash failed in [%s].",
                    __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        sample_ret = sample_sha256_update((uint8_t *)&(sp_db->vk_key),
                                     sizeof(sp_db->vk_key), sha_handle);
        if(sample_ret != SAMPLE_SUCCESS)
        {
            fprintf(stderr,"\nError, udpate hash failed in [%s].",
                    __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        sample_ret = sample_sha256_get_hash(sha_handle,
                                      (sample_sha256_hash_t *)&report_data);
        if(sample_ret != SAMPLE_SUCCESS)
        {
            fprintf(stderr,"\nError, Get hash failed in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        ret = memcmp((uint8_t *)&report_data,
                     &(p_quote->report_body.report_data),
                     sizeof(report_data));
        if(ret) {
            fprintf(stderr, "\nError, verify hash fail [%s].", __FUNCTION__);
            ret = SP_INTEGRITY_FAILED;
            break;
        }

        //call DCAP quote verify library to get supplemental data size
        dcap_ret = sgx_qv_get_quote_supplemental_data_size(&supplemental_data_size);
        if (dcap_ret == SGX_QL_SUCCESS && supplemental_data_size == sizeof(sgx_ql_qv_supplemental_t)) {
            printf("\tInfo: sgx_qv_get_quote_supplemental_data_size successfully returned.\n");
            p_supplemental_data = (uint8_t*)malloc(supplemental_data_size);
        }
        else {
            printf("\tError: sgx_qv_get_quote_supplemental_data_size failed: 0x%04x\n", dcap_ret);
            supplemental_data_size = 0;
        }

        //set current time. This is only for sample purposes, in production mode a trusted time should be used.
        current_time = time(NULL);
        //set nonce
        get_drng_support();
        if (0 != get_random(rand_nonce, sizeof(rand_nonce))) {
            fprintf(stderr,"\nfailed to get random.\n");
            ret = SP_INTERNAL_ERROR;
            break;
        }

        memcpy(qve_report_info.nonce.rand, rand_nonce, sizeof(rand_nonce));
#if 0
        // Trusted quote verification
        if (use_qve) {
            //set nonce
            //
            memcpy(qve_report_info.nonce.rand, rand_nonce, sizeof(rand_nonce));

            //get target info of SampleISVEnclave. QvE will target the generated report to this enclave.
            //
            sgx_ret = sgx_create_enclave(SAMPLE_ISV_ENCLAVE, SGX_DEBUG_FLAG, &token, &updated, &eid, NULL);
            if (sgx_ret != SGX_SUCCESS) {
                printf("\tError: Can't load SampleISVEnclave. 0x%04x\n", sgx_ret);
                return -1;
            }
            sgx_status_t get_target_info_ret;
            sgx_ret = ecall_get_target_info(eid, &get_target_info_ret, &qve_report_info.app_enclave_target_info);
            if (sgx_ret != SGX_SUCCESS || get_target_info_ret != SGX_SUCCESS) {
                printf("\tError in sgx_get_target_info. 0x%04x\n", get_target_info_ret);
            }
            else {
                printf("\tInfo: get target info successfully returned.\n");
            }

            //call DCAP quote verify library to set QvE loading policy
            //
            dcap_ret = sgx_qv_set_enclave_load_policy(SGX_QL_DEFAULT);
            if (dcap_ret == SGX_QL_SUCCESS) {
                printf("\tInfo: sgx_qv_set_enclave_load_policy successfully returned.\n");
            }
            else {
                printf("\tError: sgx_qv_set_enclave_load_policy failed: 0x%04x\n", dcap_ret);
            }


            //call DCAP quote verify library to get supplemental data size
            //
            dcap_ret = sgx_qv_get_quote_supplemental_data_size(&supplemental_data_size);
            if (dcap_ret == SGX_QL_SUCCESS) {
                printf("\tInfo: sgx_qv_get_quote_supplemental_data_size successfully returned.\n");
                p_supplemental_data = (uint8_t*)malloc(supplemental_data_size);
            }
            else {
                printf("\tError: sgx_qv_get_quote_supplemental_data_size failed: 0x%04x\n", dcap_ret);
                supplemental_data_size = 0;
            }

            //set current time. This is only for sample purposes, in production mode a trusted time should be used.
            //
            current_time = time(NULL);


            //call DCAP quote verify library for quote verification
            //here you can choose 'trusted' or 'untrusted' quote verification by specifying parameter '&qve_report_info'
            //if '&qve_report_info' is NOT NULL, this API will call Intel QvE to verify quote
            //if '&qve_report_info' is NULL, this API will call 'untrusted quote verify lib' to verify quote, this mode doesn't rely on SGX capable system, but the results can not be cryptographically authenticated
            dcap_ret = sgx_qv_verify_quote(
                quote.data(), (uint32_t)quote.size(),
                NULL,
                current_time,
                &collateral_expiration_status,
                &quote_verification_result,
                &qve_report_info,
                supplemental_data_size,
                p_supplemental_data);
            if (dcap_ret == SGX_QL_SUCCESS) {
                printf("\tInfo: App: sgx_qv_verify_quote successfully returned.\n");
            }
            else {
                printf("\tError: App: sgx_qv_verify_quote failed: 0x%04x\n", dcap_ret);
            }


            // Threshold of QvE ISV SVN. The ISV SVN of QvE used to verify quote must be greater or equal to this threshold
            // e.g. You can get latest QvE ISVSVN in QvE Identity JSON file from
            // https://api.trustedservices.intel.com/sgx/certification/v2/qve/identity
            // Make sure you are using trusted & latest QvE ISV SVN as threshold
            //
            sgx_isv_svn_t qve_isvsvn_threshold = 3;

            //call sgx_dcap_tvl API in SampleISVEnclave to verify QvE's report and identity
            //
            sgx_ret = sgx_tvl_verify_qve_report_and_identity(eid,
                &verify_qveid_ret,
                quote.data(),
                (uint32_t) quote.size(),
                &qve_report_info,
                current_time,
                collateral_expiration_status,
                quote_verification_result,
                p_supplemental_data,
                supplemental_data_size,
                qve_isvsvn_threshold);

            if (sgx_ret != SGX_SUCCESS || verify_qveid_ret != SGX_QL_SUCCESS) {
                printf("\tError: Ecall: Verify QvE report and identity failed. 0x%04x\n", verify_qveid_ret);
            }
            else {
                printf("\tInfo: Ecall: Verify QvE report and identity successfully returned.\n");
            }

            //check verification result
            //
            switch (quote_verification_result)
            {
            case SGX_QL_QV_RESULT_OK:
                printf("\tInfo: App: Verification completed successfully.\n");
                ret = 0;
                break;
            case SGX_QL_QV_RESULT_CONFIG_NEEDED:
            case SGX_QL_QV_RESULT_OUT_OF_DATE:
            case SGX_QL_QV_RESULT_OUT_OF_DATE_CONFIG_NEEDED:
            case SGX_QL_QV_RESULT_SW_HARDENING_NEEDED:
            case SGX_QL_QV_RESULT_CONFIG_AND_SW_HARDENING_NEEDED:
                printf("\tWarning: App: Verification completed with Non-terminal result: %x\n", quote_verification_result);
                ret = 1;
                break;
            case SGX_QL_QV_RESULT_INVALID_SIGNATURE:
            case SGX_QL_QV_RESULT_REVOKED:
            case SGX_QL_QV_RESULT_UNSPECIFIED:
            default:
                printf("\tError: App: Verification completed with Terminal result: %x\n", quote_verification_result);
                ret = -1;
                break;
            }
        }
#endif
        //call DCAP quote verify library for quote verification
        //here you can choose 'trusted' or 'untrusted' quote verification by specifying parameter '&qve_report_info'
        //if '&qve_report_info' is NOT NULL, this API will call Intel QvE to verify quote
        //if '&qve_report_info' is NULL, this API will call 'untrusted quote verify lib' to verify quote, this mode doesn't rely on SGX capable system, but the results can not be cryptographically authenticated
        dcap_ret = sgx_qv_verify_quote(
            (uint8_t*)p_quote, quote_size,
            NULL,
            current_time,
            &collateral_expiration_status,
            &quote_verification_result,
            NULL,
            supplemental_data_size,
            p_supplemental_data);
        if (dcap_ret == SGX_QL_SUCCESS) {
            printf("\tInfo: App: sgx_qv_verify_quote successfully returned.\n");
        }
        else {
            printf("\tError: App: sgx_qv_verify_quote failed: 0x%04x\n", dcap_ret);
            ret = -1;
            break;
        }

        printf("\tInfo: App: Verification quote_verification_result=%#x\n", quote_verification_result);

        //check verification result
        if ((quote_verification_result != SGX_QL_QV_RESULT_OK) &&
            (quote_verification_result != SGX_QL_QV_RESULT_OUT_OF_DATE)) {
            printf("verify result is not expected (%#x)\n", quote_verification_result);
            ret = -1;
            break;
        }

        // Respond the client with the results of the attestation.
        uint32_t att_result_msg_size = sizeof(sample_ra_att_result_msg_t)+SGX_DOMAIN_KEY_SIZE;
        p_att_result_msg_full =
            (ra_samp_response_header_t*)malloc(att_result_msg_size
            + sizeof(ra_samp_response_header_t) );
        if(!p_att_result_msg_full)
        {
            fprintf(stderr, "\nError, out of memory in [%s].", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }
        memset(p_att_result_msg_full, 0, att_result_msg_size+sizeof(ra_samp_response_header_t));
        p_att_result_msg_full->type = TYPE_RA_ATT_RESULT;
        p_att_result_msg_full->size = att_result_msg_size;

        p_att_result_msg = (sample_ra_att_result_msg_t *)p_att_result_msg_full->body;


        memcpy_s(p_att_result_msg->platform_info_blob.nonce.rand,sizeof(rand_nonce), rand_nonce, sizeof(rand_nonce));
        memcpy_s(&(p_att_result_msg->platform_info_blob.quote_verification_result),sizeof(sgx_ql_qv_result_t), &quote_verification_result, sizeof(sgx_ql_qv_result_t));
        memcpy_s(&(p_att_result_msg->platform_info_blob.qve_report_info),sizeof(sgx_ql_qe_report_info_t), &qve_report_info, sizeof(sgx_ql_qe_report_info_t));
        // Generate mac based on the mk key.
        mac_size = sizeof(ias_platform_info_blob_t);
        sample_ret = sample_rijndael128_cmac_msg(&sp_db->mk_key,
            (const uint8_t*)&p_att_result_msg->platform_info_blob,
            mac_size,
            &p_att_result_msg->mac);
        if(SAMPLE_SUCCESS != sample_ret)
        {
            fprintf(stderr, "\nError, cmac platform_info fail in [%s].\n", __FUNCTION__);
            ret = SP_INTERNAL_ERROR;
            break;
        }

        // Generate shared secret and encrypt it with SK, if attestation passed.
        p_att_result_msg->secret.payload_size = SGX_DOMAIN_KEY_SIZE;

        sgx_status_t enclave_ret = SGX_SUCCESS;
        ret = sgx_wrap_domain_key(g_enclave_id, &enclave_ret,
	                          &sp_db->sk_key,
                                  p_att_result_msg->secret.payload,
                                  p_att_result_msg->secret.payload_size,
                                  &p_att_result_msg->secret.payload_tag);
        if (enclave_ret != SGX_SUCCESS || ret != SGX_SUCCESS) {
            printf("Failed to get domain key.\n");
            ret = SP_INTERNAL_ERROR;
            break;
        }

    }while(0);

    if(ret) {
        *pp_att_result_msg = NULL;
        SAFE_FREE(p_att_result_msg_full);
    }
    else {
        *pp_att_result_msg = p_att_result_msg_full;
    }

    return ret;
}


int SocketDispatchCmd(
                    ra_samp_request_header_t *req,
                    ra_samp_response_header_t **p_resp) {
    printf("receive the msg type(%d) from client.\n", req->type);
    int32_t ret;

    switch (req->type) {
    case TYPE_RA_MSG1:
        printf("Dispatching TYPE_RA_MSG1, body size: %d\n", req->size);
        return sp_ra_proc_msg1_req((const sample_ra_msg1_t*)((size_t)req
            + sizeof(ra_samp_request_header_t)),
            req->size,
            req->sessionId,
            p_resp);

    case TYPE_RA_MSG3:
        printf("Dispatching TYPE_RA_MSG3, body size: %d\n", req->size);
        return sp_ra_proc_msg3_req((const sample_ra_msg3_t*)((size_t)req
            + sizeof(ra_samp_request_header_t)),
            req->size,
            req->sessionId,
            p_resp);
    case TYPE_RA_GET_SESSION_ID_REQ:
        return sp_ra_proc_get_session_id_req(p_resp);

    case TYPE_RA_FINALIZE_SESSION_ID_REQ:
        return sp_ra_proc_finalize_session_id_req(req->sessionId, p_resp);

    default:
        printf("Cannot dispatch unknown msg type %d\n", req->type);
        return ERR_NOT_IMPLEMENTED;
    }

    return ret;
}

/*
* This will handle connection for each socket client
*/
static void* SocketMsgHandler(void *sock_addr)
{
    ra_samp_request_header_t *req = NULL;
    ra_samp_response_header_t *resp = NULL;
    uint32_t req_size;

    int32_t sockfd = *(int32_t*)sock_addr;
    int32_t ret;

    /* Receive a message from client */
    while (true) {
        req_size = 0;
        if (!RecvAll(sockfd, &req_size, sizeof(req_size))) {
            printf("failed to get req_size\n");
            break;
        }
        if (req_size <= 0) //no msg need to read
            break;

        req = (ra_samp_request_header_t *)malloc(req_size);
        if (!req) {
            printf("failed to allocate req buffer\n");
            break;
        }
        memset(req, 0, req_size);
        if (!RecvAll(sockfd, req, req_size)) {
            printf("failed to get req data\n");
            break;
        }

        ret = SocketDispatchCmd(req,&resp);
        if (ret < 0 || !resp) {
            printf("failed(%d) to handle msg type(%d)\n", ret, req->type);
            SendErrResponse(sockfd, req->type, ret);

            ret = db_finalize(req->sessionId);
            if(ret!= NO_ERROR){
                fprintf(stderr, "\nError, failed in [%s].", __FUNCTION__);
                ret = SP_INTERNAL_ERROR;
                break;
            }

            SAFE_FREE(req);
            SAFE_FREE(resp);
            continue;
        }

        if (resp)
            SendResponse(sockfd, resp);

        SAFE_FREE(req);
        SAFE_FREE(resp);
    }

    return 0;
}


void Initialize() {
	log_i("Initializing ProtocolHandler [\"socket-%d\"]", server_port);
    struct sockaddr_in serAddr, cliAddr;
    int32_t listenfd, connfd;
    socklen_t cliAddr_len;
    int ret = 0;

    /* Create socket */
    listenfd = socket(AF_INET, SOCK_STREAM , 0);
    if (listenfd == -1) {
        printf("Could not create socket\n");
        return;
    }

    /* Prepare the sockaddr_in structure */
    serAddr.sin_family = AF_INET;
    serAddr.sin_addr.s_addr = INADDR_ANY;
    serAddr.sin_port = htons(server_port);

    /* Bind the server socket */
    if ((ret = bind(listenfd,(struct sockaddr *)&serAddr , sizeof(serAddr))) < 0) {
        printf("bind failed(%d)\n", ret);
        close(listenfd);
        return;
    }

    /* Listen */
    listen(listenfd , 1024);

	log_i("Starting ProtocolHandler [\"socket-%d\"]", server_port);
    log_i("Waiting for incoming connections...");
    cliAddr_len = sizeof(cliAddr);
    while (true) {
        /* Accept and incoming connection */
        connfd = accept(listenfd, (struct sockaddr *)&cliAddr, &cliAddr_len);
        if(connfd < 0) {
            printf("accept error\n");
            break;
        }

        char *ipaddr = hexToCharIP(cliAddr.sin_addr);
        if (ipaddr) {
            printf("New Client(%d) connected! IP=%s\n", connfd, ipaddr);
            free(ipaddr);
        }

        pthread_t sniffer_thread;
        if (pthread_create(&sniffer_thread, NULL, SocketMsgHandler, (void *)&connfd) < 0) {
            printf("could not create thread\n");
            break;
        }

        /* Join the thread
        * can't block here, since the main thread need to accept the other connections.
        */
        //pthread_join(sniffer_thread , NULL);
    }

    close(listenfd);

}


}
