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
#include <linux/limits.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include "secret_prov.h"
#include "cross_comm.h"
#include "clf_server.h"
#include "cmd_params.h"


log_level_t g_log_level = LOG_LEVEL_INFO;
static pthread_mutex_t g_print_lock;
char g_secret_pf_key_hex[WRAP_KEY_SIZE * 2 + 1] = {0};

struct cmd_params params;

/* network port clf_server binding */
uint16_t g_port = 4433;

/* server certification */
char g_server_cert_path[PATH_MAX] = "certs/server_signed_cert.crt";
char g_server_pri_key_path[PATH_MAX] = "certs/server_private_key.pem";

int communicate_with_client_callback(struct ra_tls_ctx* ctx);

static void hexdump_mem(const void* data, size_t size) {
	uint8_t* ptr = (uint8_t*)data;
	for (size_t i = 0; i < size; i++)
		printf("%02x", ptr[i]);
	printf("\n");
}

/*
 * specific callback to verify SGX measurements during TLS handshake
 */
static int verify_measurements_callback(const char* mrenclave, const char* mrsigner,
                                        const char* isv_prod_id, const char* isv_svn) {
	int ret = -1;	//error must be a negative value
 
	assert(mrenclave && mrsigner && isv_prod_id && isv_svn);
 
	pthread_mutex_lock(&g_print_lock);
	puts("\nReceived the following measurements from the client:");
	printf("  - MRENCLAVE:   "); hexdump_mem(mrenclave, 32);
	printf("  - MRSIGNER:    "); hexdump_mem(mrsigner, 32);
	printf("  - ISV_PROD_ID: %hu\n", *((uint16_t*)isv_prod_id));
	printf("  - ISV_SVN:     %hu\n", *((uint16_t*)isv_svn));
	pthread_mutex_unlock(&g_print_lock);
	char null_mrenclave[MRENCLAVE_LEN] = {0};
	char null_mrsigner[MRSIGNER_LEN] = {0};
	if(memcmp(params.MREnclave, null_mrenclave, MRENCLAVE_LEN)) {
		if(memcmp(params.MREnclave, mrenclave, MRENCLAVE_LEN)) {
			printf("mrenclave mismatch\n");
			return ret;
		}
	}
	if(memcmp(params.MRSigner, null_mrsigner, MRSIGNER_LEN)) {
		if(memcmp(params.MRSigner, mrsigner, MRSIGNER_LEN)) {
			printf("mrsigner mismatch\n");
			return ret;
		}
	}
	if(params.isv_prod_id!=0 && params.isv_prod_id!=*((uint16_t*)isv_prod_id)) {
		printf("isv_prod_id mismatch\n");
		return ret;
	}
	if(params.isv_svn!=0 && params.isv_svn!=*((uint16_t*)isv_svn)){
		printf("isv_svn mismatch\n");
		return ret;
	}
	return 0;
}

int main(int argc, char** argv) {
	int ret;
	ret = pthread_mutex_init(&g_print_lock, NULL);
	if (ret < 0)
		return ret;

  	int status = 1;
  	status = cmd_params_process(argc, argv, &params);
  	if (status != 0)
     		return status;
	char port[16] = {0};
	sprintf(port, "%d", params.port);
  	printf("\n");
	printf("Starting server\n\tport:\t\t%d\n\tcert_path:\t%s\n\tpri_key_path:\t%s\n",
			params.port, params.server_cert_path, params.server_private_key_path);
	ret = secret_provision_start_server((uint8_t*)params.secret, sizeof(params.secret),
										port,
										params.server_cert_path, params.server_private_key_path,
										verify_measurements_callback,
										communicate_with_client_callback);
	if (ret < 0) {
		log_error("[error] secret_provision_start_server() returned %d\n", ret);
		return 1;
	}
	pthread_mutex_destroy(&g_print_lock);
	return 0;
}
