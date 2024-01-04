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

#ifndef _ECP_INTERFACE_H
#define _ECP_INTERFACE_H

#include "sgx_ecp_types.h"
#include "sgx_tcrypto.h"

//Key Derivation Function ID : 0x0001  AES-CMAC Entropy Extraction and Key Expansion
const uint16_t AES_CMAC_KDF_ID = 0x0001;

sgx_status_t derive_key(
    const sgx_ec256_dh_shared_t* shared_key,
    const char* label,
    uint32_t label_length,
    sgx_ec_key_128bit_t* derived_key);

#ifndef INTERNAL_SGX_ERROR_CODE_CONVERTOR
#define INTERNAL_SGX_ERROR_CODE_CONVERTOR(x) if(x != SGX_ERROR_OUT_OF_MEMORY){x = SGX_ERROR_UNEXPECTED;}
#endif

#endif

