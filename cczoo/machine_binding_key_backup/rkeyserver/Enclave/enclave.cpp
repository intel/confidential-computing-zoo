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

#include "enclave_t.h"
#include "sgx_tseal.h"

#include <string>
#include <stdio.h>
#include <stdbool.h>
#include <mbusafecrt.h>

#include <assert.h>
#include "sgx_tkey_exchange.h"
#include "sgx_tcrypto.h"

#define SGX_DOMAIN_KEY_SIZE 16

// This is the public EC key of the SP.
static const sgx_ec256_public_t g_sp_pub_key = {
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

// Used to store the secret passed by the SP in the sample code.
uint8_t g_domain_key[SGX_DOMAIN_KEY_SIZE] = {0};

void printf(const char *fmt, ...) 
{
    char buf[BUFSIZ] = {'\0'};
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, BUFSIZ, fmt, ap);
    va_end(ap);
    ocall_print_string(buf);
}

sgx_status_t sgx_get_domainkey(uint8_t *domain_key)
{
    sgx_status_t ret = SGX_ERROR_UNEXPECTED;
    uint32_t dk_cipher_len = sgx_calc_sealed_data_size(0, SGX_DOMAIN_KEY_SIZE);

    if (dk_cipher_len == UINT32_MAX)
        return SGX_ERROR_UNEXPECTED;

    int retstatus;
    uint8_t dk_cipher[dk_cipher_len] = {0};
    uint8_t tmp[SGX_DOMAIN_KEY_SIZE] = {0};

    ret = ocall_read_domain_key(&retstatus, dk_cipher, dk_cipher_len);
    if (ret != SGX_SUCCESS)
        return ret;

    if (retstatus == 0) {
        uint32_t dk_len = sgx_get_encrypt_txt_len((const sgx_sealed_data_t *)dk_cipher);

        ret = sgx_unseal_data((const sgx_sealed_data_t *)dk_cipher, NULL, 0, tmp, &dk_len);
	if (ret != SGX_SUCCESS)
            return ret;
    }
    // -2: dk file does not exist.
    else if (retstatus == -2) {
        printf("enclave file does not exist.\n");
        ret = sgx_read_rand(tmp, SGX_DOMAIN_KEY_SIZE);
        if (ret != SGX_SUCCESS) {
            return ret;
        }

        ret = sgx_seal_data(0, NULL, SGX_DOMAIN_KEY_SIZE, tmp, dk_cipher_len, (sgx_sealed_data_t *)dk_cipher);
        if (ret != SGX_SUCCESS)
            return SGX_ERROR_UNEXPECTED;

        ret = ocall_store_domain_key(&retstatus, dk_cipher, dk_cipher_len);
        if (ret != SGX_SUCCESS || retstatus != 0)
            return SGX_ERROR_UNEXPECTED;
    }
    else
        return SGX_ERROR_UNEXPECTED;

    memcpy_s(domain_key, SGX_DOMAIN_KEY_SIZE, tmp, SGX_DOMAIN_KEY_SIZE);
    memset_s(tmp, SGX_DOMAIN_KEY_SIZE, 0, SGX_DOMAIN_KEY_SIZE);

    return ret;
}

/* encrypt dk with session key */
sgx_status_t sgx_wrap_domain_key(sgx_aes_gcm_128bit_key_t *p_key,
                                 uint8_t *p_dst, size_t p_dst_len,
                                 sgx_aes_gcm_128bit_tag_t *p_out_mac)
{
    uint8_t domain_key[SGX_DOMAIN_KEY_SIZE];
    uint8_t aes_gcm_iv[12] = {0};

    if (p_dst_len < SGX_DOMAIN_KEY_SIZE)
        return SGX_ERROR_UNEXPECTED;

    sgx_status_t ret = sgx_get_domainkey(domain_key);
    if (ret != SGX_SUCCESS) {
        printf("Failed to get domain:%d.\n", ret);
        return ret;
    }

    ret = sgx_rijndael128GCM_encrypt(p_key,
                                     domain_key, SGX_DOMAIN_KEY_SIZE,
                                     p_dst,
                                     aes_gcm_iv, sizeof(aes_gcm_iv),
                                     NULL, 0,
                                     p_out_mac);

    return ret;
}

// This ecall is a wrapper of sgx_ra_init to create the trusted
// KE exchange key context needed for the remote attestation
// SIGMA API's.
sgx_status_t enclave_init_ra(
    int b_pse,
    sgx_ra_context_t *p_context)
{
    // isv enclave call to trusted key exchange library.
    sgx_status_t ret;
#ifdef SUPPLIED_KEY_DERIVATION
    ret = sgx_ra_init_ex(&g_sp_pub_key, b_pse, key_derivation, p_context);
#else
    ret = sgx_ra_init(&g_sp_pub_key, b_pse, p_context);
#endif
    return ret;
}

// Closes the tKE key context used during the SIGMA key
// exchange.
sgx_status_t SGXAPI enclave_ra_close(
    sgx_ra_context_t context)
{
    sgx_status_t ret;
    ret = sgx_ra_close(context);
    return ret;
}

// Verify the mac sent in att_result_msg from the SP using the
// MK key.
sgx_status_t enclave_verify_att_result_mac(sgx_ra_context_t context,
                                   uint8_t* p_message,
                                   size_t message_size,
                                   uint8_t* p_mac,
                                   size_t mac_size)
{
    sgx_status_t ret;
    sgx_ec_key_128bit_t mk_key;

    if(mac_size != sizeof(sgx_mac_t))
    {
        ret = SGX_ERROR_INVALID_PARAMETER;
        return ret;
    }
    if(message_size > UINT32_MAX)
    {
        ret = SGX_ERROR_INVALID_PARAMETER;
        return ret;
    }

    do {
        uint8_t mac[SGX_CMAC_MAC_SIZE] = {0};

        ret = sgx_ra_get_keys(context, SGX_RA_KEY_MK, &mk_key);
        if(SGX_SUCCESS != ret)
        {
            break;
        }
        ret = sgx_rijndael128_cmac_msg(&mk_key,
                                       p_message,
                                       (uint32_t)message_size,
                                       &mac);
        if(SGX_SUCCESS != ret)
        {
            break;
        }
        if(0 == consttime_memequal(p_mac, mac, sizeof(mac)))
        {
            ret = SGX_ERROR_MAC_MISMATCH;
            break;
        }

    }
    while(0);

    return ret;
}

// Generate a secret information for the SP encrypted with SK.
sgx_status_t enclave_store_domainkey (
    sgx_ra_context_t context,
    uint8_t *p_secret,
    uint32_t secret_size,
    uint8_t *p_gcm_mac)
{
    sgx_status_t ret = SGX_SUCCESS;
    sgx_ec_key_128bit_t sk_key;
    uint32_t i;

    do {
        if(secret_size != SGX_DOMAIN_KEY_SIZE)
        {
            ret = SGX_ERROR_INVALID_PARAMETER;
            break;
        }

        ret = sgx_ra_get_keys(context, SGX_RA_KEY_SK, &sk_key);
        if(SGX_SUCCESS != ret)
        {
            break;
        }

        uint8_t aes_gcm_iv[12] = {0};
        ret = sgx_rijndael128GCM_decrypt(&sk_key,
                                         p_secret,
                                         secret_size,
                                         g_domain_key,
                                         &aes_gcm_iv[0],
                                         12,
                                         NULL,
                                         0,
                                         (const sgx_aes_gcm_128bit_tag_t *)
                                            (p_gcm_mac));

        if(ret != SGX_SUCCESS) {
            printf("Failed to decrypt the secret from server\n");
        }
        printf("Decrypt the serect success\n");
        for (i=0; i<sizeof(g_domain_key); i++) {
            printf("domain_key[%d]=%2d\n", i, g_domain_key[i]);
        }

        //store the DK
        ret = SGX_ERROR_UNEXPECTED;
        uint32_t dk_cipher_len = sgx_calc_sealed_data_size(0, SGX_DOMAIN_KEY_SIZE);

        if (dk_cipher_len == UINT32_MAX)
            return SGX_ERROR_UNEXPECTED;

        int retstatus;
        uint8_t dk_cipher[dk_cipher_len] = {0};
        uint8_t tmp[SGX_DOMAIN_KEY_SIZE] = {0};

        memcpy_s(tmp, SGX_DOMAIN_KEY_SIZE, g_domain_key, SGX_DOMAIN_KEY_SIZE);
        ret = sgx_seal_data(0, NULL, SGX_DOMAIN_KEY_SIZE, tmp, dk_cipher_len, (sgx_sealed_data_t *)dk_cipher);
        if (ret != SGX_SUCCESS)
            return SGX_ERROR_UNEXPECTED;

        ret = ocall_store_domain_key(&retstatus, dk_cipher, dk_cipher_len);
        if (ret != SGX_SUCCESS || retstatus != 0)
            return SGX_ERROR_UNEXPECTED;

        memset_s(tmp, SGX_DOMAIN_KEY_SIZE, 0, SGX_DOMAIN_KEY_SIZE);

    } while(0);

    return ret;
}
