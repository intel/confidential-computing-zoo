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

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "clf_client.h"

int test_secret_prov_connect();

int get_data_push_result_test()
{
	for(int i=0; i<1000; i++) {
		printf("--------- test IN. i=%d---------\n", i);
		signed char ip_port[] = "localhost:4433";
		signed char ca_cert[] = "certs/ca_cert.crt";
		int8_t key[64] = {0};
		get_key(ip_port, ca_cert, key, 64);
		printf("key=%s\n", key);

		char *fname = "README.md";
		int64_t len = 0;
		get_file_size(ip_port, ca_cert, fname, &len);
		printf("len=%lu\n", len);

		int8_t* data = (int8_t*)malloc(len);
		if(!data) {
			printf("malloc(%lu) fail\n", len);
			return -1;
		}
		memset(data, 0, len);
		int32_t ret_len = 0;
		get_file_2_buff(ip_port, ca_cert, "README.md", 2, data, 10, &ret_len);
		printf("read_len=%d, data=%s\n", ret_len, data);

		put_result(ip_port, ca_cert, "1.dat", 0, data, 20, &ret_len);

		free(data);
		data = 0;
		printf("\ntest out\n");
	}

	return 0;
}

int test_localfs() {
	int64_t len;

	char fname[] = "/plain/plain.txt";
	int8_t local[] = LOCAL_FS;
	int8_t ca[] = "";

	get_file_size(local, ca, fname, &len);

	printf("len=%ld\n", len);

	int8_t *buf = malloc(len);
	int32_t ret_len = 0;
	get_file_2_buff(local, ca, fname, 0, buf, len, &ret_len);
	printf("buf=%s\n", buf);

	printf("write plain dir\n");
	put_result(local, ca, "./plain/out.dat", 0, buf, len, &ret_len);

	remove("/encryption/out2.dat");
	printf("write encrytion dir\n");
	put_result(local, ca, "/encryption/out2.dat", 0, buf, len, &ret_len);

	return 0;
}

int loop_test() {
	for(int i=0; i<1000; i++) {
		test_secret_prov_connect();
	}
	return 0;
}

int main()
{
	test_localfs();
	//loop_test();
	getchar();
}


