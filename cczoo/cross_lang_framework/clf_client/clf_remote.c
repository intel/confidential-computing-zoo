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

#define start_secret_prov()		\
	do{\
		ret = secret_provision_start((const char *)ip_port, (const char *)ca_cert, &ctx);\
		if (ret < 0) {\
			log_error("[error] secret_provision_start() returned %d\n", ret);\
			goto out;\
		}\
	}while(0)

#define clean_secret_prov()		\
	do{\
		secret_provision_destroy();\
		secret_provision_close(&ctx);\
	}while(0)


/*
 * Get the symmetric key for input data decryption  and result encryption
 */
int get_key(int8_t* ip_port, int8_t* ca_cert, int8_t* key, int32_t key_len) {
	int ret = STATUS_FAIL;
	struct ra_tls_ctx ctx = {0};
	uint8_t* secret = NULL;
	size_t secret_size = 0;

	if(!ip_port || !ca_cert || !key) {
		return STATUS_BAD_PARAM;
	}

	/* connect server */
	start_secret_prov();

	ret = secret_provision_get(&secret, &secret_size);
	if (ret < 0) {
		log_error("[error] secret_provision_get() returned %d\n", ret);
		goto out;
	}
	if (!secret_size) {
		ret = STATUS_FAIL;
		log_error("[error] secret_provision_get() returned secret with size 0\n");
		goto out;
	}

	secret[secret_size - 1] = '\0';

	log_error("secret_size:%lu secret:%s\n", secret_size, secret);
	if (key_len < secret_size) {
		log_error("Failed. key_len(%d) < secret_size(%lu)\n", key_len, secret_size);
		ret = STATUS_FAIL;
		goto out;
	}

	memcpy(key, secret, key_len<secret_size?key_len:secret_size);

	ret = STATUS_SUCCESS;
out:
	log_errcode(ret);
	clean_secret_prov();
	return ret;
}

/*
 * Get file size so client can allocate buffer correspondingly
 */
int remote_get_file_size(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t* ret_len) {
	int ret = STATUS_FAIL;
	int bytes;
	struct ra_tls_ctx ctx = {0};
	msg_req_t req = {0};
	msg_resp_t resp = {0};

	if(!ip_port || !ca_cert || !fname || !ret_len) {
		return STATUS_BAD_PARAM;
	}

	/* connect server */
	start_secret_prov();

	ret = STATUS_FAIL;
	req.msg_type = MSG_GET_DATA_SIZE;
	req.data_len = 0;
	strncpy((char*)req.get_size.fname, fname, MAX_FNAME_LEN-1);
	bytes = secret_provision_write(&ctx, (uint8_t*)&req, sizeof(msg_req_t));
	if (bytes < 0) {
		log_error("[error] secret_provision_write() returned %d\n", bytes);
		goto out;
	}

	/* get size from source  */
	bytes = secret_provision_read(&ctx, (uint8_t*)&resp, sizeof(msg_resp_t));
	if (bytes != sizeof(msg_resp_t) || STATUS_SUCCESS != resp.status) {
		log_error("[error] secret_provision_read() returned %d (expected %lu) resp.status=%X\n",
			bytes, sizeof(msg_resp_t), resp.status);
		goto out;
	}

	if(ret_len)
		*ret_len = resp.get_size.len;

	ret = STATUS_SUCCESS;
out:
	clean_secret_prov();
	return ret;
}

/*
 * Get file from server
 */
int remote_get_file_2_buff(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len) {
	int ret = STATUS_FAIL;
	int bytes;
	struct ra_tls_ctx ctx = {0};
	msg_req_t req = {0};
	msg_resp_t resp = {0};

	if(!ip_port || !ca_cert || !fname || !data || !ret_len) {
		return STATUS_BAD_PARAM;
	}

	/* connect server */
	start_secret_prov();

	ret = STATUS_FAIL;
	req.msg_type = MSG_GET_DATA;
	req.data_len = 0;
	req.get_data.offset = offset;
	req.get_data.len = len;
	strncpy((char*)req.get_data.fname, fname, MAX_FNAME_LEN-1);
	bytes = secret_provision_write(&ctx, (uint8_t*)&req, sizeof(msg_req_t));
	if (bytes < 0) {
		log_error("[error] secret_provision_write() returned %d\n", bytes);
		goto out;
	}

	/* get data from source  */
	bytes = secret_provision_read(&ctx, (uint8_t*)&resp, sizeof(msg_resp_t));
	if (bytes != sizeof(msg_resp_t) || STATUS_SUCCESS != resp.status) {
		log_error("[error] secret_provision_read() returned %d (expected %lu) resp.status=%X\n",
			bytes, sizeof(msg_resp_t), resp.status);
		goto out;
	}

	uint64_t data_len = len < resp.get_data.data_len ? len : resp.get_data.data_len;
	bytes = secret_provision_read(&ctx, (uint8_t*)data, data_len);
	if (bytes != data_len) {
		log_error("[error] secret_provision_read() returned %d (expected %lu)\n",
			bytes, data_len);
		goto out;
	}

	if(ret_len) {
		*ret_len = data_len;
	}

	ret = STATUS_SUCCESS;
out:
	clean_secret_prov();
	return ret;
}

/*
 * Put result to server
 */
int remote_put_result(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len) {
	int ret = STATUS_FAIL;
	int bytes;
	struct ra_tls_ctx ctx = {0};
	msg_req_t req = {0};
	msg_resp_t resp = {0};

	if(!ip_port || !ca_cert || !fname || !data) {
		return STATUS_BAD_PARAM;
	}

	/* connect server */
	start_secret_prov();

	ret = STATUS_FAIL;
	req.msg_type = MSG_PUT_RESULT;
	req.data_len = len;
	req.put_res.offset = offset;
	req.put_res.len = len;
	strncpy((char*)req.put_res.fname, fname, MAX_FNAME_LEN-1);
	bytes = secret_provision_write(&ctx, (uint8_t*)&req, sizeof(msg_req_t));
	if (bytes < 0) {
		log_error("[error] secret_provision_write() returned %d\n", bytes);
		goto out;
	}

	bytes = secret_provision_write(&ctx, (uint8_t*)data, len);
	if (bytes != len) {
		log_error("[error] secret_provision_write() returned %d, expect %d\n", bytes, len);
		goto out;
	}

	/* get response */
	bytes = secret_provision_read(&ctx, (uint8_t*)&resp, sizeof(msg_resp_t));
	if (bytes != sizeof(msg_resp_t) || STATUS_SUCCESS != resp.status) {
		log_error("[error] secret_provision_read() returned %d (expected %lu) resp.status=%X\n",
			bytes, sizeof(msg_resp_t), resp.status);
		goto out;
	}

	if(ret_len) {
		*ret_len = resp.put_res.received_len;
	}

	ret = STATUS_SUCCESS;
out:
	clean_secret_prov();
	return ret;
}
