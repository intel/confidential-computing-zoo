/* SPDX-License-Identifier: LGPL-3.0-or-later */
/* Copyright (C) 2020 Intel Labs */

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include "secret_prov.h"
#include "cross_comm.h"
#include "ra_server.h"

#define MAX_FILE_RW_BUF_SIZE		(4*1024*1024)
#define MIN_FILE_RW_BUF_SIZE		(64*1024)

/*
 * response for MSG_GET_DATA
 */
int send_data(struct ra_tls_ctx* ctx, msg_req_t *req) {
	int ret = STATUS_FAIL;
	msg_resp_t resp = {0};
	uint8_t* buf = 0;
 
	if(!ctx || !req)
		return STATUS_FAIL;

	/* get valid transmission length */
	int64_t f_len = get_file_size((char*)req->get_data.fname);
	if(f_len <= 0) {
		resp.get_data.data_len = 0;
		resp.status = STATUS_FAIL;
	} else {
		if(req->get_data.offset + req->get_data.len < f_len) {
			resp.get_data.data_len = req->get_data.len;
		} else {
			resp.get_data.data_len = f_len - req->get_data.offset;
		}
		resp.status = STATUS_SUCCESS;
	}

	/* send control struct */
	int bytes = secret_provision_write(ctx, (uint8_t*)&resp, sizeof(resp));
	if (bytes < 0) {
		fprintf(stderr, "[error] secret_provision_write(resp) returned %d\n", bytes);
		ret = STATUS_NET_SEND_FAIL;
		goto out;
	}

	/* alloc buf */
	uint64_t buf_size = MAX_FILE_RW_BUF_SIZE;
	while(!buf) {
		buf = (uint8_t*)malloc(buf_size);
		if(buf)
			break;
		buf_size /= 2;
		if(buf_size < MIN_FILE_RW_BUF_SIZE) {
			ret = STATUS_OUT_OF_MEM;
			goto out;
		}
	}
	memset(buf, 0, buf_size);

	/* send data */
	if(resp.get_data.data_len > 0) {
		int64_t sent_len = 0;
		int64_t len = 0;
		for(; sent_len < resp.get_data.data_len; sent_len += len) {
			len = buf_size < (resp.get_data.data_len-sent_len) ? buf_size : (resp.get_data.data_len-sent_len);
			/* re-set len to real length read from file in case not all len is read */
			len = fileread(req->get_data.fname, req->get_data.offset + sent_len, buf, len);
			if(0 == len) {
				break;
			}
			bytes = secret_provision_write(ctx, buf, len);
			if (bytes < 0) {
				fprintf(stderr, "[error] secret_provision_write(data) returned %d\n", bytes);
				ret = STATUS_NET_SEND_FAIL;
				goto out;
			}
		}
	}

	ret = STATUS_SUCCESS;
out:
	if(buf)
		free(buf);
	return ret;
}

/*
 * response for MSG_GET_DATA_SIZE
 */
int send_size(struct ra_tls_ctx* ctx, msg_req_t *req) {
	int ret = STATUS_FAIL;
	msg_resp_t resp = {0};
 
	if(!ctx || !req)
		return STATUS_FAIL;

	/* get valid transmission length */
	int64_t f_len = get_file_size((char*)req->get_size.fname);
	if(f_len <= 0) {
		resp.get_size.len = 0;
		resp.status = STATUS_FAIL;
	} else {
		resp.get_size.len = f_len;
		resp.status = STATUS_SUCCESS;
	}

	/* send control struct */
	int bytes = secret_provision_write(ctx, (uint8_t*)&resp, sizeof(resp));
	if (bytes < 0) {
		fprintf(stderr, "[error] secret_provision_write(resp) returned %d\n", bytes);
		ret = STATUS_NET_SEND_FAIL;
		goto out;
	}

	ret = STATUS_SUCCESS;
out:
	return ret;
}

/*
 * response for MSG_PUT_RESULT
 */
int put_result(struct ra_tls_ctx* ctx, msg_req_t *req) {
	int ret = STATUS_FAIL;
	msg_resp_t resp = {0};
	uint8_t* buf = 0;
	int64_t bytes = 0;

	if(!ctx || !req)
		return STATUS_FAIL;

	/* alloc buf */
	uint64_t buf_size = MAX_FILE_RW_BUF_SIZE;
	while(!buf) {
		buf = (uint8_t*)malloc(buf_size);
		if(buf)
			break;
		buf_size /= 2;
		if(buf_size < MIN_FILE_RW_BUF_SIZE) {
			ret = STATUS_OUT_OF_MEM;
			goto out;
		}
	}
	memset(buf, 0, buf_size);

	/* receive data */
	int64_t received = 0;
	int64_t len = 0;
	while( received < req->put_res.len ) {
		len = buf_size < (req->put_res.len-received) ? buf_size : (req->put_res.len-received);
		/*
		 * secret_provision_read guarantees all len bytes can be received, namely bytes == len,
		 * otherwise it returns failure: -ECONNRESET
		 */
		bytes = secret_provision_read(ctx, (uint8_t *)buf, len);
		if (bytes < 0) {
			if (bytes == -ECONNRESET) {
				fprintf(stderr, "[error] secret_provision_read() connection reset\n");
				resp.status = STATUS_FAIL;
				goto resp_result;
			}

			fprintf(stderr, "[error] secret_provision_read() returned %ld\n", bytes);
			resp.status = STATUS_FAIL;
			goto resp_result;
		}

		len = filewrite(req->put_res.fname, req->put_res.offset + received, buf, len);
		/* return failure if not all the bytes been written */
		if(bytes != len) {
			resp.status = STATUS_FAIL;;
			goto resp_result;
		}

		received += bytes;
	}

	resp.status = STATUS_SUCCESS;
	ret = STATUS_SUCCESS;
resp_result:
	/* send resp struct */
	resp.put_res.received_len = received;
	bytes = secret_provision_write(ctx, (uint8_t*)&resp, sizeof(resp));
	if (bytes < 0) {
		fprintf(stderr, "[error] secret_provision_write(resp) returned %ld\n", bytes);
		ret = STATUS_NET_SEND_FAIL;
		goto out;
	}

out:
	if(buf)
		free(buf);
	return ret;
}

/* this callback is called in a new thread associated with a client; be careful to make this code
 * thread-local and/or thread-safe */
int communicate_with_client_callback(struct ra_tls_ctx* ctx) {
	int ret;
	msg_req_t req = {0};
	int bytes;

	fprintf(stderr, "communicate_with_client_callback IN\n");
	/* if we reached this callback, the first secret was sent successfully */
	//printf("--- Sent secret1 = '%s' ---\n", g_secret_pf_key_hex);

	while (1) {
		bytes = secret_provision_read(ctx, (uint8_t *)&req, sizeof(msg_req_t));
		if (bytes < 0) {
			if (bytes == -ECONNRESET) {
				fprintf(stderr, "[error] secret_provision_read() connection reset\n");
				ret = STATUS_SUCCESS;
				goto out;
			}

			fprintf(stderr, "[error] secret_provision_read() returned %d\n", bytes);
			ret = STATUS_FAIL;
			goto out;
		}

		switch (req.msg_type) {
		case MSG_GET_DATA:
			ret = send_data(ctx, &req);
			break;
		case MSG_GET_DATA_SIZE:
			ret = send_size(ctx, &req);
			break;
		case MSG_PUT_RESULT:
			ret = put_result(ctx, &req);
			break;
		default:
			break;
		}
	}

	ret = 0;
out:
	fprintf(stderr, "communicate_with_client_callback OUT\n");
	secret_provision_close(ctx);
	return ret;
}

