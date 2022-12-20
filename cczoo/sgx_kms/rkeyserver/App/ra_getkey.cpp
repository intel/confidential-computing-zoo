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

#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
#include <arpa/inet.h>

#include <ra_getkey.h>
#include "log_utils.h"

#include <netdb.h>
#include <error.h>
#include "enclave_u.h"

// Needed to call untrusted key exchange library APIs, i.e. sgx_ra_proc_msg2.
#include "sgx_ukey_exchange.h"

// Needed to create enclave and do ecall.
#include "sgx_urts.h"

// Needed to query extended epid group id.
#include "sgx_uae_epid.h"
#include "sgx_uae_quote_ex.h"
#include "log_utils.h"

using namespace std;

sgx_enclave_id_t g_enclave_id;

namespace ra_getkey {

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

static bool RecvAll(int32_t sock, void *data, int32_t data_size)
{
    char *data_ptr = (char*) data;
    int32_t bytes_recv;

    while (data_size > 0)
    {
        bytes_recv = recv(sock, data_ptr, data_size, 0);
        if (bytes_recv == 0) {
            printf("the server side may closed...\n");
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

static int32_t SendAndRecvMsg(int32_t sockfd,
    const ra_samp_request_header_t *p_req,
    ra_samp_response_header_t **p_resp)
{
    ra_samp_response_header_t* out_msg;
    int req_size, resp_size = 0;
    int32_t err = NO_ERROR;

    if((NULL == p_req) ||
        (NULL == p_resp))
    {
        return -1;
    }

    /* Send a message to server */
    req_size = sizeof(ra_samp_request_header_t)+p_req->size; // req_head + req_body

    if (!SendAll(sockfd, &req_size, sizeof(req_size))) { //send req_size
        printf("send req_size failed\n");
        err = ERR_GENERIC;
        goto out;
    }
    if (!SendAll(sockfd, p_req, req_size)) { //send req
        printf("send req buffer failed\n");
        err = ERR_GENERIC;
        goto out;
    }

    /* Receive a message from server */
    if (!RecvAll(sockfd, &resp_size, sizeof(resp_size))) {
        printf("failed to get the resp size\n");
        err = ERR_GENERIC;
        goto out;
    }

    if (resp_size <= 0) {
        printf("no msg need to read\n");
        err = ERR_GENERIC;
        goto out;
    }
    out_msg = (ra_samp_response_header_t *)malloc(resp_size);
    if (!out_msg) {
        printf("allocate out_msg failed\n");
        err = ERR_NO_MEMORY;
        goto out;
    }
    if (!RecvAll(sockfd, out_msg, resp_size)) {
        printf("failed to get the data\n");
        err = ERR_GENERIC;
        goto out;
    }

    *p_resp = out_msg;
out:
    return err;
}

static int RetreiveDomainKey(int32_t sockfd) {
    ra_samp_request_header_t* p_sessionId_req = NULL;
    ra_samp_response_header_t* p_sessionId_res = NULL;
    ra_samp_request_header_t *p_msg1_full = NULL;
    ra_samp_response_header_t *p_msg2_full = NULL;
    ra_samp_request_header_t* p_msg3_full = NULL;
    ra_samp_response_header_t* p_att_result_msg_full = NULL;

    sample_ra_att_result_msg_t *p_att_result_msg_body = NULL;
    ra_samp_request_header_t* p_finalize_sessionId_req = NULL;
    ra_samp_response_header_t* p_finalize_sessionId_res = NULL;

    sgx_ra_msg2_t* p_msg2_body = NULL;
    sgx_ra_msg3_t *p_msg3 = NULL;
    sesion_id_t sessionID = {0};

    uint32_t msg3_size = 0;
    int busy_retry_time = 4;
    int enclave_lost_retry_time = 1;
    sgx_ra_context_t context = INT_MAX; //uint32_t
    sgx_status_t status = SGX_SUCCESS;
    int ret = -1;

    sgx_att_key_id_t selected_key_id = {0}; //acutally not used in our case

    do {
        ret = enclave_init_ra(g_enclave_id,
                          &status,
                          false,
                          &context);
     //Ideally, this check would be around the full attestation flow.
    } while (SGX_ERROR_ENCLAVE_LOST == ret && enclave_lost_retry_time--);

    if(SGX_SUCCESS != ret || status) {
        ret = -1;
        log_e("Error, call enclave_init_ra failed.");
        goto CLEANUP;
    }

    // call initsession and get sessionid
    // stroe sessionid to g_sessionid
    // msg1\msg3 will add sessionid in their header
    p_sessionId_req = (ra_samp_request_header_t*)
                     malloc(sizeof(ra_samp_request_header_t));
    if(NULL == p_sessionId_req) {
        ret = -1;
        goto CLEANUP;
    }
    p_sessionId_req->type = TYPE_RA_GET_SESSION_ID_REQ;
    p_sessionId_req->size = 0;
    SendAndRecvMsg(sockfd, p_sessionId_req, &p_sessionId_res);
    if(!p_sessionId_res) {
        log_e("Error, get session id failed.");
        ret = -1;
        goto CLEANUP;
    }
    if(TYPE_RA_GET_SESSION_ID_RES != p_sessionId_res->type) {
        log_e("Error, Session id response type is not matched!");
        ret = -1;
        goto CLEANUP;
    }
    log_d("session id recieved success!");
    memcpy_s(sessionID, SESSION_ID_SIZE, p_sessionId_res->sessionId, SESSION_ID_SIZE);

    /* Allocate MSG1 buf to call libukey_exchange API to retrieve MSG1 */
    p_msg1_full = (ra_samp_request_header_t*)
                 malloc(sizeof(ra_samp_request_header_t)
                        + sizeof(sgx_ra_msg1_t));
    if(NULL == p_msg1_full) {
        ret = -1;
        goto CLEANUP;
    }
    p_msg1_full->type = TYPE_RA_MSG1;
    p_msg1_full->size = sizeof(sgx_ra_msg1_t);
    memcpy_s(p_msg1_full->sessionId, SESSION_ID_SIZE, sessionID, SESSION_ID_SIZE);

    do
    {
        ret = sgx_ra_get_msg1_ex(&selected_key_id, context, g_enclave_id, sgx_ra_get_ga,
                             (sgx_ra_msg1_t*)((uint8_t*)p_msg1_full
                             + sizeof(ra_samp_request_header_t)));
        //sleep(3); // Wait 3s between retries
    } while (SGX_ERROR_BUSY == ret && busy_retry_time--);

    if(SGX_SUCCESS != ret) {
        log_e("Error, call sgx_ra_get_msg1_ex failed(%#x)", ret);
        ret = -1;
        goto CLEANUP;
    }
    log_d("Call sgx_ra_get_msg1_ex success, the MSG1 body generated.");

    log_d("Sending MSG1 to remote attestation service provider, and expecting MSG2 back...");
    SendAndRecvMsg(sockfd, p_msg1_full, &p_msg2_full);
    if(!p_msg2_full) {
        log_e("Error,sending MSG1 failed.");
        ret = -1;
        goto CLEANUP;
    }

    /* Successfully sent MSG1 and received a MSG2 back. */
    if(TYPE_RA_MSG2 != p_msg2_full->type) {
        log_e("Error, MSG2's type is not matched!");
        ret = -1;
        goto CLEANUP;
    }

    //PRINT_BYTE_ARRAY(OUTPUT, p_msg2_full, (uint32_t)sizeof(ra_samp_response_header_t) + p_msg2_full->size);
    log_d("MSG2 recieved success!");

    /* Call lib key_u(t)exchange(sgx_ra_proc_msg2_ex) to process the MSG2 and retrieve MSG3 back. */
    p_msg2_body = (sgx_ra_msg2_t*)((uint8_t*)p_msg2_full + sizeof(ra_samp_response_header_t));

    busy_retry_time = 2;
    do
    {
        ret = sgx_ra_proc_msg2_ex(&selected_key_id,
                           context,
                           g_enclave_id,
                           sgx_ra_proc_msg2_trusted,
                           sgx_ra_get_msg3_trusted,
                           p_msg2_body,
                           p_msg2_full->size,
                           &p_msg3,
                           &msg3_size);
    } while (SGX_ERROR_BUSY == ret && busy_retry_time--);
    if(!p_msg3 || (SGX_SUCCESS != (sgx_status_t)ret)) {
        log_e("Error(%d), call sgx_ra_proc_msg2_ex failed, p_msg3 = 0x%p.", ret, p_msg3);
        goto CLEANUP;
    }
    log_d("Call sgx_ra_proc_msg2_ex success.");

    p_msg3_full = (ra_samp_request_header_t*)malloc(sizeof(ra_samp_request_header_t) + msg3_size);
    if(NULL == p_msg3_full) {
        ret = -1;
        goto CLEANUP;
    }
    p_msg3_full->type = TYPE_RA_MSG3;
    p_msg3_full->size = msg3_size;
    memcpy_s(p_msg3_full->sessionId, SESSION_ID_SIZE, sessionID, SESSION_ID_SIZE);

    if(memcpy_s(p_msg3_full->body, msg3_size, p_msg3, msg3_size)) {
        log_e("Error: memcpy failed.");
        ret = -1;
        goto CLEANUP;
    }

    // The ISV application sends msg3 to the SP to get the attestation
    // result message, attestation result message needs to be freed when
    // no longer needed. The ISV service provider decides whether to use
    // linkable or unlinkable signatures. The format of the attestation
    // result is up to the service provider. This format is used for
    // demonstration.  Note that the attestation result message makes use
    // of both the MK for the MAC and the SK for the secret. These keys are
    // established from the SIGMA secure channel binding.
    log_d("Sending MSG3 to remote attestation service provider,"
                        "expecting attestation result msg back...");
    SendAndRecvMsg(sockfd, p_msg3_full, &p_att_result_msg_full);
    if(ret || !p_att_result_msg_full) {
        ret = -1;
        log_e("Error, sending MSG3 failed.");
        goto CLEANUP;
    }

    p_att_result_msg_body = (sample_ra_att_result_msg_t *)((uint8_t*)p_att_result_msg_full
                           + sizeof(ra_samp_response_header_t));
    if(TYPE_RA_ATT_RESULT != p_att_result_msg_full->type) {
        ret = -1;
        log_e("Error, the attestaion MSG's type is not matched!");
        goto CLEANUP;
    }

    log_d("Attestation result MSG recieved success!");

    /*
    * Check the MAC using MK on the attestation result message.
    * The format of the attestation result message is specific(sample_ra_att_result_msg_t).
    */
    ret = enclave_verify_att_result_mac(g_enclave_id,
            &status,
            context,
            (uint8_t*)&p_att_result_msg_body->platform_info_blob,
            sizeof(ias_platform_info_blob_t),
            (uint8_t*)&p_att_result_msg_body->mac,
            sizeof(sgx_mac_t));
    if((SGX_SUCCESS != ret) ||
       (SGX_SUCCESS != status)) {
        ret = -1;
        log_e("Error: Attestation result MSG's MK based cmac check failed");
        goto CLEANUP;
    }

    log_d("Verify attestation result is succeed!");

    ret = enclave_store_domainkey(g_enclave_id,
                          &status,
                          context,
                          p_att_result_msg_body->secret.payload,
                          p_att_result_msg_body->secret.payload_size,
                          p_att_result_msg_body->secret.payload_tag);
    if((SGX_SUCCESS != ret)  || (SGX_SUCCESS != status)) {
        log_e("Error(%d), decrypt secret using SK based on AES-GCM failed.", ret);
        ret = -1;
        goto CLEANUP;
    }

    // after domainkey verify, call finalize session id
    p_finalize_sessionId_req = (ra_samp_request_header_t*)
                     malloc(sizeof(ra_samp_request_header_t));
    if(NULL == p_finalize_sessionId_req) {
        ret = -1;
        goto CLEANUP;
    }
    p_finalize_sessionId_req->type = TYPE_RA_FINALIZE_SESSION_ID_REQ;
    p_finalize_sessionId_req->size = 0;
    memcpy_s(p_finalize_sessionId_req->sessionId, SESSION_ID_SIZE, sessionID, SESSION_ID_SIZE);
    SendAndRecvMsg(sockfd, p_finalize_sessionId_req, &p_finalize_sessionId_res);
    if(!p_finalize_sessionId_res) {
        log_e("Error, send finalize session id failed.");
        ret = -1;
        goto CLEANUP;
    }
    if(TYPE_RA_FINALIZE_SESSION_ID_RES != p_finalize_sessionId_res->type) {
        log_e("Error, finalize session id response type is not matched!");
        ret = -1;
        goto CLEANUP;
    }
    log_d("call finalize session id success!");

CLEANUP:
    // Clean-up
    // Need to close the RA key state.
    if(INT_MAX != context) {
        int ret_save = ret;
        ret = enclave_ra_close(g_enclave_id, &status, context);
        if(SGX_SUCCESS != ret || status) {
            log_e("Error, call enclave_ra_close fail [%#x].",ret);
        }
        else {
            // enclave_ra_close was successful, let's restore the value that
            // led us to this point in the code.
            ret = ret_save;
        }
        log_d("Call enclave_ra_close success.");
    }
    SAFE_FREE(p_sessionId_req);
    SAFE_FREE(p_sessionId_res);
    SAFE_FREE(p_msg1_full);
    SAFE_FREE(p_msg2_full);
    SAFE_FREE(p_msg3);
    SAFE_FREE(p_msg3_full);
    SAFE_FREE(p_att_result_msg_full);
    SAFE_FREE(p_finalize_sessionId_req);
    SAFE_FREE(p_finalize_sessionId_res);

    return ret;
}

int32_t Initialize_ra(std::string deploy_ip_addr, uint32_t deploy_port) {
    log_i("Applying for a DomainKey from KMS domainKey server.");
    int32_t ret = -1;
    int32_t retry_count = 5;
    struct sockaddr_in serAddr;
    int32_t sockfd = -1;

    sockfd = socket(AF_INET, SOCK_STREAM, 0);
    if(sockfd < 0) {
        printf("Create socket failed\n");
        exit(1);
    }
    bzero(&serAddr, sizeof(serAddr));
    serAddr.sin_family = AF_INET;
    serAddr.sin_port = htons(deploy_port);
    serAddr.sin_addr.s_addr = inet_addr(deploy_ip_addr.c_str());

    do {
        if(connect(sockfd, (struct sockaddr*)&serAddr, sizeof(serAddr)) >= 0) {
            break;
        }
        else if (retry_count > 0) {
            log_w("Failed to Connect rkeyserver, sleep 0.5s and try again...\n");
            usleep(500000); // 0.5 s
        }
        else {
            log_e("Failed to connect rkeyserver\n");
            goto out;
        }
    } while (retry_count-- > 0);

    /* retrieve the domain key from rkeyserver via remote secure channel */
    ret = RetreiveDomainKey(sockfd);
    if (ret != 0) {
        log_e("Failed(%d) to setup the secure channel.\n", ret);
        goto out;
    }
    
    log_i("Successfully received the DomainKey from deploy server.");

out:
    close(sockfd);
    return ret;
}

}
