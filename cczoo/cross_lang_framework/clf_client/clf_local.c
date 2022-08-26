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

/*
 * Get file size so client can allocate buffer correspondingly
 */
int local_get_file_size(char* fname, int64_t* ret_len) {
	int ret = STATUS_FAIL;

	if(!fname || !ret_len) {
		return STATUS_BAD_PARAM;
	}

	int64_t f_len = filesize(fname);
	if(f_len < 0) {
		ret = STATUS_FAIL;
		goto out;
	}

	if(ret_len) {
		*ret_len = f_len;
	}

	ret = STATUS_SUCCESS;
out:
	return ret;
}

/*
 * Get file from local filesystem
 */
int local_get_file_2_buff(char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len) {
	int bytes;

	if(!fname || !data || len<0) {
		return STATUS_BAD_PARAM;
	}

	if(len == 0) {
		return STATUS_SUCCESS;
	}

	/* get data from source  */
	bytes = fileread(fname, offset, data, len);
	/*
	bytes = len;
	log_error("local_get_file_2_buff->%s, offset=%ld, len=%d\n", fname, offset, len);
	memset(data, 0, len);
	*/

	if(ret_len) {
		*ret_len = bytes;
	}

	return STATUS_SUCCESS;
}

/*
 * Put result to local filesystem
 */
int local_put_result(char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len) {
	int ret = STATUS_FAIL;
	int bytes = 0;

	if(!fname || !data || offset<0 || len<0) {
		return STATUS_BAD_PARAM;
	}

	if(len == 0) {
		return STATUS_SUCCESS;
	}

	bytes = filewrite(fname, offset, data, len);

	if(ret_len) {
		*ret_len = bytes;
	}

	if(bytes != len) {
		ret = STATUS_FAIL;
		goto out;
	}

	ret = STATUS_SUCCESS;
out:
	return ret;
}

