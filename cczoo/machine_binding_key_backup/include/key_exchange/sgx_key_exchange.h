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

#ifndef _SGX_KEY_EXCHANGE_H_
#define _SGX_KEY_EXCHANGE_H_

#include <stdint.h>
#include "sgx_quote.h"
#include "sgx_ecp_types.h"

#ifdef  __cplusplus
extern "C" {
#endif

typedef struct _ps_sec_prop_desc
{
    uint8_t  sgx_ps_sec_prop_desc[256];
} sgx_ps_sec_prop_desc_t;

typedef uint32_t sgx_ra_context_t;

typedef sgx_key_128bit_t sgx_ra_key_128_t;

typedef enum _ra_key_type_t
{
    SGX_RA_KEY_SK = 1,
    SGX_RA_KEY_MK,
} sgx_ra_key_type_t;

typedef struct _ra_msg1_t
{
    sgx_ec256_public_t       g_a;         /* the Endian-ness of Ga is Little-Endian */
    sgx_epid_group_id_t      gid;         /* the Endian-ness of GID is Little-Endian */
} sgx_ra_msg1_t;


typedef struct _ra_msg2_t
{
    sgx_ec256_public_t       g_b;         /* the Endian-ness of Gb is Little-Endian */
    sgx_spid_t               spid;
    uint16_t                 quote_type;  /* unlinkable Quote(0) or linkable Quote(1) in little endian*/
    uint16_t                 kdf_id;      /* key derivation function id in little endian. */
    sgx_ec256_signature_t    sign_gb_ga;  /* In little endian */
    sgx_mac_t                mac;         /* mac_smk(g_b||spid||quote_type||kdf_id||sign_gb_ga) */
    uint32_t                 sig_rl_size;
    uint8_t                  sig_rl[];
} sgx_ra_msg2_t;

typedef struct _ra_msg3_t
{
    sgx_mac_t                mac;         /* mac_smk(g_a||ps_sec_prop||quote) */
    sgx_ec256_public_t       g_a;         /* the Endian-ness of Ga is Little-Endian */
    sgx_ps_sec_prop_desc_t   ps_sec_prop; /* reserved Must be 0 */
    uint8_t                  quote[];
} sgx_ra_msg3_t;

#ifdef  __cplusplus
}
#endif

#endif
