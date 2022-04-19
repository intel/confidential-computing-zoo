#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "clf_client.h"

int main()
{
	printf("test IN\n");
	//secret_prov_test();
	uint8_t key[64] = {0};
	get_key(key, 64);
	printf("key=%s\n", key);

	char *fname = "README.md";
	uint64_t len = 0;
	get_file_size(fname, &len);
	printf("len=%lu\n", len);

	uint8_t* data = (uint8_t*)malloc(len);
	if(!data) {
		printf("malloc(%lu) fail\n", len);
		return -1;
	}
	memset(data, 0, len);
	uint64_t ret_len = 0;
	get_file_2_buff("README.md", 2, data, 10, &ret_len);
	printf("read_len=%ld, data=%s\n", ret_len, data);
	get_file_2_buff("README.md", 0, data, 20, &ret_len);
	printf("read_len=%ld, data=%s\n", ret_len, data);

	put_result("1.dat", 0, data, 20);

	printf("\ntest out\n");
}

