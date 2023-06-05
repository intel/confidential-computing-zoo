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

#ifndef __STDINT_LIMITS
#define __STDINT_LIMITS
#endif
//for Linux
#ifndef __STDC_LIMIT_MACROS
#define __STDC_LIMIT_MACROS
#endif
#include <stdint.h>
#include <stdlib.h>

#include "se_memcpy.h"
#include "sgx_ukey_exchange.h"
#include "sgx_uae_epid.h"
#include "sgx_uae_quote_ex.h"
#include "sgx_ecp_types.h"
#include "se_lock.hpp"

#include "se_cdefs.h"
#include <stdio.h>
#include "sgx_quote_3.h"
#include "sgx_ql_lib_common.h"
#include "sgx_dcap_ql_wrapper.h"

SGX_ACCESS_VERSION(ukey_exchange, 1)

static sgx_att_key_id_t g_att_key_id;
static sgx_target_info_t g_qe_target_info;
static Mutex g_ukey_spin_lock;


#ifndef ERROR_BREAK
#define ERROR_BREAK(x)  if(x){break;}
#endif
#ifndef SAFE_FREE
#define SAFE_FREE(ptr) {if (NULL != (ptr)) {free(ptr); (ptr)=NULL;}}
#endif

sgx_status_t sgx_ra_get_msg1(
    sgx_ra_context_t context,
    sgx_enclave_id_t eid,
    sgx_ecall_get_ga_trusted_t p_get_ga,
    sgx_ra_msg1_t *p_msg1)
{
    if(!p_msg1 || !p_get_ga)
        return SGX_ERROR_INVALID_PARAMETER;
    sgx_epid_group_id_t gid = {0};
    sgx_target_info_t qe_target_info;

    memset(&qe_target_info, 0, sizeof(qe_target_info));
    sgx_status_t ret = sgx_init_quote(&qe_target_info, &gid);
    if(SGX_SUCCESS != ret)
        return ret;
    g_ukey_spin_lock.lock();
    memset(&g_att_key_id, 0, sizeof(sgx_att_key_id_t));
    if(memcpy_s(&g_qe_target_info, sizeof(g_qe_target_info),
             &qe_target_info, sizeof(qe_target_info)) != 0)
    {
        g_ukey_spin_lock.unlock();
        return SGX_ERROR_UNEXPECTED;
    }
    g_ukey_spin_lock.unlock();
    if(memcpy_s(&p_msg1->gid, sizeof(p_msg1->gid), &gid, sizeof(gid)) != 0)
        return SGX_ERROR_UNEXPECTED;
    sgx_ec256_public_t g_a;
    sgx_status_t status = SGX_ERROR_UNEXPECTED;
    memset(&g_a, 0, sizeof(g_a));
    ret = p_get_ga(eid, &status, context, &g_a);
    if(SGX_SUCCESS !=ret)
        return ret;
    if (SGX_SUCCESS != status)
        return status;
    memcpy_s(&p_msg1->g_a, sizeof(p_msg1->g_a), &g_a, sizeof(g_a));
    return SGX_SUCCESS;
}

sgx_status_t sgx_ra_proc_msg2(
    sgx_ra_context_t context,
    sgx_enclave_id_t eid,
    sgx_ecall_proc_msg2_trusted_t p_proc_msg2,
    sgx_ecall_get_msg3_trusted_t p_get_msg3,
    const sgx_ra_msg2_t *p_msg2,
    uint32_t msg2_size,
    sgx_ra_msg3_t **pp_msg3,
    uint32_t *p_msg3_size)
{
    if(!p_msg2 || !p_proc_msg2 || !p_get_msg3 || !p_msg3_size || !pp_msg3)
        return SGX_ERROR_INVALID_PARAMETER;
    if(msg2_size != sizeof(sgx_ra_msg2_t) + p_msg2->sig_rl_size)
        return SGX_ERROR_INVALID_PARAMETER;

    sgx_status_t ret = SGX_ERROR_UNEXPECTED;
    sgx_report_t report;
    sgx_ra_msg3_t *p_msg3 = NULL;
    sgx_att_key_id_t empty_att_key_id;

    memset(&report, 0, sizeof(report));
    memset(&empty_att_key_id, 0, sizeof(empty_att_key_id));

    {
        sgx_quote_nonce_t nonce;
        sgx_report_t qe_report;
        sgx_target_info_t qe_target_info;

        memset(&nonce, 0, sizeof(nonce));
        memset(&qe_report, 0, sizeof(qe_report));

        sgx_status_t status;
        g_ukey_spin_lock.lock();
        if(0 != memcmp(&g_att_key_id, &empty_att_key_id, sizeof(g_att_key_id)))
        {
            ret = SGX_ERROR_INVALID_STATE;
            g_ukey_spin_lock.unlock();
            goto CLEANUP;
        }
        if(memcpy_s(&qe_target_info, sizeof(qe_target_info),
                 &g_qe_target_info, sizeof(g_qe_target_info)) != 0)
        {
            ret = SGX_ERROR_UNEXPECTED;
            g_ukey_spin_lock.unlock();
            goto CLEANUP;
        }
        g_ukey_spin_lock.unlock();
        ret = p_proc_msg2(eid, &status, context, p_msg2, &qe_target_info,
                          &report, &nonce);
        if(SGX_SUCCESS!=ret)
        {
            goto CLEANUP;
        }
        if(SGX_SUCCESS!=status)
        {
            ret = status;
            goto CLEANUP;
        }

        uint32_t quote_size = 0;
        ret = sgx_calc_quote_size(p_msg2->sig_rl_size ?
                                    const_cast<uint8_t *>(p_msg2->sig_rl):NULL,
                                 p_msg2->sig_rl_size,
                                 &quote_size);
        if(SGX_SUCCESS!=ret)
        {
            goto CLEANUP;
        }

        //check integer overflow of quote_size
        if (UINT32_MAX - quote_size < sizeof(sgx_ra_msg3_t))
        {
            ret = SGX_ERROR_UNEXPECTED;
            goto CLEANUP;
        }
        uint32_t msg3_size = static_cast<uint32_t>(sizeof(sgx_ra_msg3_t)) + quote_size;
        p_msg3 = (sgx_ra_msg3_t *)malloc(msg3_size);
        if(!p_msg3)
        {
            ret = SGX_ERROR_OUT_OF_MEMORY;
            goto CLEANUP;
        }
        memset(p_msg3, 0, msg3_size);

        ret = sgx_get_quote(&report,
                           p_msg2->quote_type == SGX_UNLINKABLE_SIGNATURE ?
                               SGX_UNLINKABLE_SIGNATURE : SGX_LINKABLE_SIGNATURE,
                           const_cast<sgx_spid_t *>(&p_msg2->spid),
                           &nonce,
                           p_msg2->sig_rl_size ?
                               const_cast<uint8_t *>(p_msg2->sig_rl):NULL,
                           p_msg2->sig_rl_size,
                           &qe_report,
                           (sgx_quote_t *)p_msg3->quote,
                           quote_size);
        if(SGX_SUCCESS!=ret)
        {
            goto CLEANUP;
        }

        ret = p_get_msg3(eid, &status, context, quote_size, &qe_report,
                         p_msg3, msg3_size);
        if(SGX_SUCCESS!=ret)
        {
            goto CLEANUP;
        }
        if(SGX_SUCCESS!=status)
        {
            ret = status;
            goto CLEANUP;
        }
        *pp_msg3 = p_msg3;
        *p_msg3_size = msg3_size;
    }

CLEANUP:
    if(ret)
        SAFE_FREE(p_msg3);
    return ret;
}

sgx_status_t SGXAPI sgx_ra_get_msg1_ex(
	const sgx_att_key_id_t *p_att_key_id,
	sgx_ra_context_t context,
	sgx_enclave_id_t eid,
	sgx_ecall_get_ga_trusted_t p_get_ga,
    sgx_ra_msg1_t *p_msg1)
{
    sgx_status_t ret = SGX_SUCCESS;
    quote3_error_t qe3_ret = SGX_QL_SUCCESS;

    if(!p_msg1 || !p_get_ga || !p_att_key_id)
        return SGX_ERROR_INVALID_PARAMETER;

    sgx_target_info_t qe_target_info;

    memset(&qe_target_info, 0, sizeof(qe_target_info));
    qe3_ret = sgx_qe_get_target_info(&qe_target_info);
    if (SGX_QL_SUCCESS != qe3_ret) {
        printf("Error in sgx_qe_get_target_info. 0x%04x\n", qe3_ret);
        ret = SGX_ERROR_UNEXPECTED;
        return ret;
    }

    g_ukey_spin_lock.lock();
    if(memcpy_s(&g_qe_target_info, sizeof(g_qe_target_info),
             &qe_target_info, sizeof(qe_target_info)) != 0)
    {
        g_ukey_spin_lock.unlock();
        return SGX_ERROR_UNEXPECTED;
    }
    g_ukey_spin_lock.unlock();
    memset(&p_msg1->gid, 0, sizeof(p_msg1->gid));

    sgx_ec256_public_t g_a;
    sgx_status_t status = SGX_ERROR_UNEXPECTED;
    memset(&g_a, 0, sizeof(g_a));
    ret = p_get_ga(eid, &status, context, &g_a);
    if(SGX_SUCCESS !=ret)
        return ret;
    if (SGX_SUCCESS != status)
        return status;
    memcpy_s(&p_msg1->g_a, sizeof(p_msg1->g_a), &g_a, sizeof(g_a));
    return SGX_SUCCESS;
}

sgx_status_t SGXAPI sgx_ra_proc_msg2_ex(
	const sgx_att_key_id_t *p_att_key_id,
	sgx_ra_context_t context,
	sgx_enclave_id_t eid,
	sgx_ecall_proc_msg2_trusted_t p_proc_msg2,
	sgx_ecall_get_msg3_trusted_t p_get_msg3,
	const sgx_ra_msg2_t *p_msg2,
	uint32_t msg2_size,
	sgx_ra_msg3_t **pp_msg3,
	uint32_t *p_msg3_size)
{
    if(!p_msg2 || !p_proc_msg2 || !p_get_msg3 || !p_msg3_size || !pp_msg3 || !p_att_key_id)
        return SGX_ERROR_INVALID_PARAMETER;
    if(p_msg2->sig_rl_size)
        return SGX_ERROR_UNEXPECTED; // No SigRL for ECDSA attestation
    if(msg2_size != sizeof(sgx_ra_msg2_t) + p_msg2->sig_rl_size)
        return SGX_ERROR_INVALID_PARAMETER;

    uint32_t quote_size = 0;
    quote3_error_t qe3_ret = SGX_QL_SUCCESS;
    sgx_status_t ret = SGX_ERROR_UNEXPECTED;
    sgx_report_t report;
    sgx_ra_msg3_t *p_msg3 = NULL;

    memset(&report, 0, sizeof(report));
    {
        sgx_quote_nonce_t nonce;
        sgx_target_info_t qe_target_info;

        memset(&nonce, 0, sizeof(nonce));

        sgx_status_t status;
        g_ukey_spin_lock.lock();
        if(0 != memcmp(&g_att_key_id, p_att_key_id, sizeof(g_att_key_id)))
        {
            ret = SGX_ERROR_INVALID_STATE;
            g_ukey_spin_lock.unlock();
            goto CLEANUP;
        }
        if(memcpy_s(&qe_target_info, sizeof(qe_target_info),
                 &g_qe_target_info, sizeof(g_qe_target_info)) != 0)
        {
            ret = SGX_ERROR_UNEXPECTED;
            g_ukey_spin_lock.unlock();
            goto CLEANUP;
        }
        g_ukey_spin_lock.unlock();

        ret = p_proc_msg2(eid, &status, context, p_msg2, &qe_target_info,
                          &report, &nonce);
        if(SGX_SUCCESS!=ret)
        {
            goto CLEANUP;
        }
        if(SGX_SUCCESS!=status)
        {
            ret = status;
            goto CLEANUP;
        }

        qe3_ret = sgx_qe_get_quote_size(&quote_size);
        if (SGX_QL_SUCCESS != qe3_ret) {
            printf("Error in sgx_qe_get_quote_size. 0x%04x\n", qe3_ret);
            ret =SGX_ERROR_UNEXPECTED;
            goto CLEANUP;
        }

        //check integer overflow of quote_size
        if (UINT32_MAX - quote_size < sizeof(sgx_ra_msg3_t))
        {
            ret = SGX_ERROR_UNEXPECTED;
            goto CLEANUP;
        }
        uint32_t msg3_size = static_cast<uint32_t>(sizeof(sgx_ra_msg3_t)) + quote_size;
        p_msg3 = (sgx_ra_msg3_t *)malloc(msg3_size);
        if(!p_msg3)
        {
            ret = SGX_ERROR_OUT_OF_MEMORY;
            goto CLEANUP;
        }
        memset(p_msg3, 0, msg3_size);

        qe3_ret = sgx_qe_get_quote(&report, quote_size, p_msg3->quote);
        if (SGX_QL_SUCCESS != qe3_ret) {
            printf( "Error in sgx_qe_get_quote. 0x%04x\n", qe3_ret);
            ret = SGX_ERROR_UNEXPECTED;
            goto CLEANUP;
        }

        //sgx_report_t* qe_report is NULL for ECDSA
        ret = p_get_msg3(eid, &status, context, quote_size, NULL, p_msg3, msg3_size);
        if(SGX_SUCCESS!=ret)
        {
            goto CLEANUP;
        }
        if(SGX_SUCCESS!=status)
        {
            ret = status;
            goto CLEANUP;
        }

        *pp_msg3 = p_msg3;
        *p_msg3_size = msg3_size;
    }

    CLEANUP:
        if(ret)
            SAFE_FREE(p_msg3);
        return ret;
}

