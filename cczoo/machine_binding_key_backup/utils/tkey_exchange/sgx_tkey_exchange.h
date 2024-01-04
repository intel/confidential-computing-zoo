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

#ifndef _SGX_TKEY_EXCHANGE_H_
#define _SGX_TKEY_EXCHANGE_H_

#include "sgx.h"
#include "sgx_defs.h"
#include "sgx_key_exchange.h"

#ifdef  __cplusplus
extern "C" {
#endif

/*
 * The sgx_ra_init function creates a context for the remote attestation and
 * key exchange process.
 *
 * @param p_pub_key The EC public key of the service provider based on the NIST
 *                  P-256 elliptic curve.
 * @param b_pse     [DEPRECATED]
 * @param p_context The output context for the subsequent remote attestation
 *                  and key exchange process, to be used in sgx_ra_get_msg1 and
 *                  sgx_ra_proc_msg2.
 * @return sgx_status_t SGX_SUCCESS                     Indicates success.
 *                      SGX_ERROR_INVALID_PARAMETER     Indicates an error that
 *                                                      the input parameters are
 *                                                      invalid.
 *                      SGX_ERROR_OUT_OF_MEMORY         There is not enough
 *                                                      memory available to
 *                                                      complete this operation.
 *                      SGX_ERROR_AE_SESSION_INVALID    Session is invalid or
 *                                                      ended by server.
 *                      SGX_ERROR_UNEXPECTED            Indicates an unexpected
 *                                                      error occurs.
 */
sgx_status_t SGXAPI sgx_ra_init(
    const sgx_ec256_public_t *p_pub_key,
    int b_pse,
    sgx_ra_context_t *p_context);

/*
 * The sgx_ra_derive_secret_keys_t function should takes the Diffie-Hellman
 * shared secret as input to allow the ISV enclave to generate their own derived
 * shared keys (SMK, SK, MK and VK).
 *
 * @param p_shared_key The the Diffie-Hellman shared secret.
 * @param kdf_id,      Key Derivation Function ID 
 * @param p_smk_key    The output SMK.
 * @param p_sk_key     The output SK.
 * @param p_mk_key     The output MK.
 * @param p_vk_key     The output VK.
 * @return sgx_status_t SGX_SUCCESS                     Indicates success.
 *                      SGX_ERROR_INVALID_PARAMETER     Indicates an error that
 *                                                      the input parameters are
 *                                                      invalid.
 *                      SGX_ERROR_KDF_MISMATCH          Indicates key derivation
 *                                                      function doesn't match.
 *                      SGX_ERROR_OUT_OF_MEMORY         There is not enough
 *                                                      memory available to
 *                                                      complete this operation.
 *                      SGX_ERROR_UNEXPECTED            Indicates an unexpected
 *                                                      error occurs.
 */

typedef sgx_status_t(*sgx_ra_derive_secret_keys_t)(
    const sgx_ec256_dh_shared_t* p_shared_key,
    uint16_t kdf_id,
    sgx_ec_key_128bit_t* p_smk_key,
    sgx_ec_key_128bit_t* p_sk_key,
    sgx_ec_key_128bit_t* p_mk_key,
    sgx_ec_key_128bit_t* p_vk_key);

/*
 * The sgx_ra_init_ex function creates a context for the remote attestation and
 * key exchange process asociated with a key derive function.
 *
 * @param p_pub_key The EC public key of the service provider based on the NIST
 *                  P-256 elliptic curve.
 * @param b_pse     [DEPRECATED]
 * @param derive_key_cb A pointer to a call back routine matching the
 *                      function prototype of sgx_ra_derive_secret_keys_t.  This
 *                      function takes the Diffie-Hellman shared secret as input
 *                      to allow the ISV enclave to generate their own derived
 *                      shared keys (SMK, SK, MK and VK).
 * @param p_context The output context for the subsequent remote attestation
 *                  and key exchange process, to be used in sgx_ra_get_msg1 and
 *                  sgx_ra_proc_msg2.
 * @return sgx_status_t SGX_SUCCESS                     Indicates success.
 *                      SGX_ERROR_INVALID_PARAMETER     Indicates an error that
 *                                                      the input parameters are
 *                                                      invalid.
 *                      SGX_ERROR_OUT_OF_MEMORY         There is not enough
 *                                                      memory available to
 *                                                      complete this operation.
 *                      SGX_ERROR_AE_SESSION_INVALID    Session is invalid or
 *                                                      ended by server.
 *                      SGX_ERROR_UNEXPECTED            Indicates an unexpected
 *                                                      error occurs.
 */

sgx_status_t SGXAPI sgx_ra_init_ex(
    const sgx_ec256_public_t *p_pub_key,
    int b_pse,
    sgx_ra_derive_secret_keys_t derive_key_cb,
    sgx_ra_context_t *p_context);
/*
 * The sgx_ra_get_keys function is used to get the negotiated keys of a remote
 * attestation and key exchange session. This function should only be called
 * after the service provider accepts the remote attestation and key exchange
 * protocol message 3 produced by sgx_ra_proc_msg2.
 *
 * @param context   Context returned by sgx_ra_init.
 * @param type      The specifier of keys, can be SGX_RA_KEY_MK, SGX_RA_KEY_SK.
 * @param p_key     The key returned.
 * @return sgx_status_t SGX_SUCCESS                     Indicates success.
 *                      SGX_ERROR_INVALID_PARAMETER     Indicates an error that
 *                                                      the input parameters are
 *                                                      invalid.
 *                      SGX_ERROR_INVALID_STATE         Indicates this function
 *                                                      is called out of order.
 */
sgx_status_t SGXAPI sgx_ra_get_keys(
    sgx_ra_context_t context,
    sgx_ra_key_type_t type,
    sgx_ra_key_128_t *p_key);

/*
 * Call the sgx_ra_close function to release the remote attestation and key
 * exchange context after the process is done and the context isn't needed
 * anymore.
 *
 * @param context   Context returned by sgx_ra_init.
 * @return sgx_status_t SGX_SUCCESS                     Indicates success.
 *                      SGX_ERROR_INVALID_PARAMETER     Indicates an error that
 *                                                      the input parameters are
 *                                                      invalid.
 */
sgx_status_t SGXAPI sgx_ra_close(
    sgx_ra_context_t context);

#ifdef  __cplusplus
}
#endif

#endif
