#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "clf_client.h"

int main()
{
	printf("test IN\n");
	signed char ip_port[] = "VM-0-3-ubuntu:4433";
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
	get_file_2_buff(ip_port, ca_cert, "README.md", 0, data, 20, &ret_len);
	printf("read_len=%d, data=%s\n", ret_len, data);

	put_result(ip_port, ca_cert, "1.dat", 0, data, 20);

	printf("\ntest out\n");
}

