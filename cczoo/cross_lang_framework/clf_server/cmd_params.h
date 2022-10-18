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
#ifndef __CMD_PARAMS_h__
#define __CMD_PARAMS_h__

#include <linux/limits.h>
#define WRAP_KEY_SIZE	16
#define MRSIGNER_LEN	32
#define MRENCLAVE_LEN	32
struct cmd_params {
    const char MRSigner[MRSIGNER_LEN];
    const char MREnclave[MRENCLAVE_LEN];
    uint16_t isv_prod_id;
    uint16_t isv_svn;
    const char secret[WRAP_KEY_SIZE];
    const char port[8];
    const char server_cert_path[PATH_MAX];
    const char server_private_key_path[PATH_MAX];
};

/**
 * Function for parsing command-line parameters of quote_gen
 *
 */
int cmd_params_process(int argc, char **argv, struct cmd_params *params);
