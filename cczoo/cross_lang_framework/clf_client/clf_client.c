/* SPDX-License-Identifier: LGPL-3.0-or-later */
/* Copyright (C) 2020 Intel Labs */

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

/*
 * Get the symmetric key for input data decryption  and result encryption
 */
int get_key(int8_t* key, int32_t key_len) {
	int ret = STATUS_FAIL;
	struct ra_tls_ctx ctx = {0};
	uint8_t* secret = NULL;
	size_t secret_size = 0;

	log_error("key[0]:%d key[1]:%d key_len:%d sizeof(msg_type_t):%lu\n", key[0], key[1], key_len, sizeof(msg_type_t));

	/* secret provisioning was not run as part of initialization, run it now */
	ret = secret_provision_start("VM-0-3-ubuntu:4433",
								 "certs/ca_cert.crt", &ctx);
	if (ret < 0) {
		log_error("[error] secret_provision_start() returned %d\n", ret);
		goto out;
	}

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
		ret = STATUS_FAIL;
		goto out;
	}

	memcpy(key, secret, secret_size);
	ret = STATUS_SUCCESS;
out:
	secret_provision_destroy();
	secret_provision_close(&ctx);
	return ret;
}

/*
 * Get file size so client can allocate buffer correspondingly
 */
int get_file_size(char* fname, int64_t* ret_len) {
	int ret = STATUS_FAIL;
	int bytes;
	struct ra_tls_ctx ctx = {0};
	msg_req_t req = {0};
	msg_resp_t resp = {0};

	ret = secret_provision_start("VM-0-3-ubuntu:4433",
                                 "certs/ca_cert.crt", &ctx);	//TODO: should NOT hardcode target machine
	if (ret < 0) {
		fprintf(stderr, "[error] secret_provision_start() returned %d\n", ret);
		goto out;
	}

	ret = STATUS_FAIL;
	req.msg_type = MSG_GET_DATA_SIZE;
	req.data_len = 0;
	strncpy((char*)req.get_size.fname, fname, MAX_FNAME_LEN-1);
	bytes = secret_provision_write(&ctx, (uint8_t*)&req, sizeof(msg_req_t));
	if (bytes < 0) {
		fprintf(stderr, "[error] secret_provision_write() returned %d\n", bytes);
		goto out;
	}

	/* get size from source  */
	bytes = secret_provision_read(&ctx, (uint8_t*)&resp, sizeof(msg_resp_t));
	if (bytes != sizeof(msg_resp_t) || STATUS_SUCCESS != resp.status) {
		fprintf(stderr, "[error] secret_provision_read() returned %d (expected %lu) resp.status=%X\n",
			bytes, sizeof(msg_resp_t), resp.status);
		goto out;
	}

	if(ret_len)
		*ret_len = resp.get_size.len;

	ret = STATUS_SUCCESS;
out:
	secret_provision_destroy();
	secret_provision_close(&ctx);
	return ret;
}

/*
 * Get file from server
 */
int get_file_2_buff(char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len) {
	int ret = STATUS_FAIL;
	int bytes;
	struct ra_tls_ctx ctx = {0};
	msg_req_t req = {0};
	msg_resp_t resp = {0};

	ret = secret_provision_start("VM-0-3-ubuntu:4433",
								 "certs/ca_cert.crt", &ctx);	//TODO: should NOT hardcode target machine
	if (ret < 0) {
		fprintf(stderr, "[error] secret_provision_start() returned %d\n", ret);
		goto out;
	}

	ret = STATUS_FAIL;
	req.msg_type = MSG_GET_DATA;
	req.data_len = 0;
	req.get_data.offset = offset;
	req.get_data.len = len;
	strncpy((char*)req.get_data.fname, fname, MAX_FNAME_LEN-1);
	bytes = secret_provision_write(&ctx, (uint8_t*)&req, sizeof(msg_req_t));
	if (bytes < 0) {
		fprintf(stderr, "[error] secret_provision_write() returned %d\n", bytes);
		goto out;
	}

	/* get data from source  */
	bytes = secret_provision_read(&ctx, (uint8_t*)&resp, sizeof(msg_resp_t));
	if (bytes != sizeof(msg_resp_t) || STATUS_SUCCESS != resp.status) {
		fprintf(stderr, "[error] secret_provision_read() returned %d (expected %lu) resp.status=%X\n",
			bytes, sizeof(msg_resp_t), resp.status);
		goto out;
	}

	uint64_t data_len = len < resp.get_data.data_len ? len : resp.get_data.data_len;
	bytes = secret_provision_read(&ctx, (uint8_t*)data, data_len);
	if (bytes != data_len) {
		fprintf(stderr, "[error] secret_provision_read() returned %d (expected %lu)\n",
			bytes, data_len);
		goto out;
	}

	if(ret_len) {
		*ret_len = data_len;
	}

	ret = STATUS_SUCCESS;
out:
	secret_provision_destroy();
	secret_provision_close(&ctx);
	return ret;
}

/*
 * Put result to server
 */
int put_result(char* fname, int64_t offset, int8_t* data, int32_t len) {
	int ret = STATUS_FAIL;
	int bytes;
	struct ra_tls_ctx ctx = {0};
	msg_req_t req = {0};
	msg_resp_t resp = {0};

	ret = secret_provision_start("VM-0-3-ubuntu:4433",
								 "certs/ca_cert.crt", &ctx);	//TODO: should NOT hardcode target machine
	if (ret < 0) {
		fprintf(stderr, "[error] secret_provision_start() returned %d\n", ret);
		goto out;
	}

	ret = STATUS_FAIL;
	req.msg_type = MSG_PUT_RESULT;
	req.data_len = len;
	req.put_res.offset = offset;
	req.put_res.len = len;
	strncpy((char*)req.put_res.fname, fname, MAX_FNAME_LEN-1);
	bytes = secret_provision_write(&ctx, (uint8_t*)&req, sizeof(msg_req_t));
	if (bytes < 0) {
		fprintf(stderr, "[error] secret_provision_write() returned %d\n", bytes);
		goto out;
	}

	bytes = secret_provision_write(&ctx, (uint8_t*)data, len);
	if (bytes != len) {
		fprintf(stderr, "[error] secret_provision_write() returned %d, expect %d\n", bytes, len);
		goto out;
	}

	/* get response */
	bytes = secret_provision_read(&ctx, (uint8_t*)&resp, sizeof(msg_resp_t));
	if (bytes != sizeof(msg_resp_t) || STATUS_SUCCESS != resp.status) {
		fprintf(stderr, "[error] secret_provision_read() returned %d (expected %lu) resp.status=%X\n",
			bytes, sizeof(msg_resp_t), resp.status);
		goto out;
	}

	ret = STATUS_SUCCESS;
out:
	secret_provision_destroy();
	secret_provision_close(&ctx);
	return ret;
}
