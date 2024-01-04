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

#ifndef _SOCKET_SERVER_H_
#define _SOCKET_SERVER_H_

#include <cstdint>
#include <vector>
#include <memory>

#include "sample_ra_msg.h"

using namespace std;

namespace socket_server {

const uint32_t server_port = 8888;

#ifndef SAFE_FREE
#define SAFE_FREE(ptr) {if (NULL != (ptr)) {free(ptr); (ptr) = NULL;}}
#endif

int sp_ra_proc_msg1_req(const sample_ra_msg1_t *p_msg1,
                        uint32_t msg1_size,
                        const sesion_id_t sessionId,
                        ra_samp_response_header_t **pp_msg2);

int sp_ra_proc_msg3_req(const sample_ra_msg3_t *p_msg3,
                        uint32_t msg3_size,
                        const sesion_id_t sessionId,
                        ra_samp_response_header_t **pp_att_result_msg);

int sp_ra_proc_get_session_id_req(ra_samp_response_header_t **pp_session_res);

int sp_ra_proc_finalize_session_id_req(const sesion_id_t sessionId,
                                       ra_samp_response_header_t **pp_finalize_session_res);

/* initialize the socket handle */
void Initialize();

}

#endif

