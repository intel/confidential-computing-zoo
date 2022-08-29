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

#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>

#include "secret_prov.h"
#include "cross_comm.h"
#include "clf_client.h"

log_level_t g_log_level = LOG_LEVEL_INFO;

static bool is_local(int8_t* ip_port) {
	if(strcmp((char*)ip_port, LOCAL_FS)) {
		return false;
	}
	return true;
}

/*
 * Get file size so client can allocate buffer correspondingly
 */
int get_file_size(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t* ret_len) {
	if(is_local(ip_port)) {
		return local_get_file_size(fname, ret_len);
	} else {
		return remote_get_file_size(ip_port, ca_cert, fname, ret_len);
	}
}

/*
 * Get file from server
 */
int get_file_2_buff(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len) {
	if(is_local(ip_port)) {
		return local_get_file_2_buff(fname, offset, data, len, ret_len);
	} else {
		return remote_get_file_2_buff(ip_port, ca_cert, fname, offset, data, len, ret_len);
	}
}

/*
 * Put result to server
 */
int put_result(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len) {
	if(is_local(ip_port)) {
		return local_put_result(fname, offset, data, len, ret_len);
	} else {
		return remote_put_result(ip_port, ca_cert, fname, offset, data, len, ret_len);
	}
}
