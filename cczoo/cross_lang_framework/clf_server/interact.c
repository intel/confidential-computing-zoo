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
#include "clf_server.h"

#define MAX_FILE_RW_BUF_SIZE		(4*1024*1024)
#define MIN_FILE_RW_BUF_SIZE		(64*1024)

/*
 * response for MSG_GET_DATA
 */
int send_data(struct ra_tls_ctx* ctx, msg_req_t *req) {
	int ret = STATUS_FAIL;
	msg_resp_t resp = {0};
	int8_t* buf = 0;

	log_debug("Request: MSG_GET_DATA\n");

	if(!ctx || !req)
		return STATUS_FAIL;

	/* get valid transmission length */
	int64_t f_len = filesize((char*)req->get_data.fname);
	if(f_len < 0) {
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
		log_error("[error] secret_provision_write(resp) returned %d\n", bytes);
		ret = STATUS_NET_SEND_FAIL;
		goto out;
	}

	/* alloc buf */
	uint64_t buf_size = MAX_FILE_RW_BUF_SIZE;
	while(!buf) {
		buf = (int8_t*)malloc(buf_size);
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
			len = fileread((char*)req->get_data.fname, req->get_data.offset + sent_len, buf, len);
			if(0 == len) {
				break;
			}
			bytes = secret_provision_write(ctx, (uint8_t*)buf, len);
			if (bytes < 0) {
				log_error("[error] secret_provision_write(data) returned %d\n", bytes);
				ret = STATUS_NET_SEND_FAIL;
				goto out;
			}
		}
	}

	ret = STATUS_SUCCESS;
out:
	if(buf)
		free(buf);

	log_errcode(ret);
	return ret;
}

/*
 * response for MSG_GET_DATA_SIZE
 */
int send_size(struct ra_tls_ctx* ctx, msg_req_t *req) {
	int ret = STATUS_FAIL;
	msg_resp_t resp = {0};

	log_debug("Request: MSG_GET_DATA_SIZE\n");

	if(!ctx || !req)
		return STATUS_FAIL;

	/* get valid transmission length */
	int64_t f_len = filesize((char*)req->get_size.fname);
	if(f_len < 0) {
		resp.get_size.len = 0;
		resp.status = STATUS_FAIL;
	} else {
		resp.get_size.len = f_len;
		resp.status = STATUS_SUCCESS;
	}

	/* send control struct */
	int bytes = secret_provision_write(ctx, (uint8_t*)&resp, sizeof(resp));
	if (bytes < 0) {
		log_error("[error] secret_provision_write(resp) returned %d\n", bytes);
		ret = STATUS_NET_SEND_FAIL;
		goto out;
	}

	ret = STATUS_SUCCESS;
out:
	log_errcode(ret);
	return ret;
}

/*
 * response for MSG_PUT_RESULT
 */
int put_result(struct ra_tls_ctx* ctx, msg_req_t *req) {
	int ret = STATUS_FAIL;
	msg_resp_t resp = {0};
	int8_t* buf = 0;
	int64_t bytes = 0;

	log_debug("Request: MSG_PUT_RESULT\n");

	if(!ctx || !req)
		return STATUS_FAIL;

	/* alloc buf */
	uint64_t buf_size = MAX_FILE_RW_BUF_SIZE;
	while(!buf) {
		buf = (int8_t*)malloc(buf_size);
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
				printf("Connection closed\n");
				resp.status = STATUS_FAIL;
				goto resp_result;
			}

			log_error("[error] secret_provision_read() returned %ld\n", bytes);
			resp.status = STATUS_FAIL;
			goto resp_result;
		}

		len = filewrite((char*)req->put_res.fname, req->put_res.offset + received, buf, len);
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
		log_error("[error] secret_provision_write(resp) returned %ld\n", bytes);
		ret = STATUS_NET_SEND_FAIL;
		goto out;
	}

out:
	if(buf)
		free(buf);
	log_errcode(ret);
	return ret;
}

int socket_cnt = 0;
int get_data_req_cnt = 0;
int get_size_req_cnt = 0;
int put_result_req_cnt = 0;
int invalid_req_cnt = 0;

/* this callback is called in a new thread associated with a client; be careful to make this code
 * thread-local and/or thread-safe */
int communicate_with_client_callback(struct ra_tls_ctx* ctx) {
	int ret;
	msg_req_t req = {0};
	int bytes;

	log_info("total_req_cnt=%d\n", ++socket_cnt);

	while (1) {
		bytes = secret_provision_read(ctx, (uint8_t *)&req, sizeof(msg_req_t));
		if (bytes < 0) {
			if (bytes == -ECONNRESET) {
				//printf("Connection closed\n");
				ret = STATUS_SUCCESS;
				goto out;
			}

			log_error("[error] secret_provision_read() returned %d\n", bytes);
			ret = STATUS_FAIL;
			goto out;
		}

		switch (req.msg_type) {
		case MSG_GET_DATA:
			log_info("get_data_req_cnt=%d\n", ++get_data_req_cnt);
			ret = send_data(ctx, &req);
			break;
		case MSG_GET_DATA_SIZE:
			log_info("get_size_req_cnt=%d\n", ++get_size_req_cnt);
			ret = send_size(ctx, &req);
			break;
		case MSG_PUT_RESULT:
			log_info("put_result_req_cnt=%d\n", ++put_result_req_cnt);
			ret = put_result(ctx, &req);
			break;
		default:
			log_error("invalid_req_cnt=%d\n", ++invalid_req_cnt);
			break;
		}
	}

	ret = 0;
out:
	secret_provision_close(ctx);
	return ret;
}

