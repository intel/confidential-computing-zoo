#ifndef __CLS_CLIENT_h__
#define __CLS_CLIENT_h__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

int get_key(uint8_t* key, uint32_t key_len);
int get_file_2_buff(char* fname, uint64_t offset, uint8_t* data, uint64_t len, uint64_t* ret_len);
int get_file_size(char* fname, uint64_t* ret_len);
int put_result(char* fname, uint64_t offset, uint8_t* data, int32_t len);

#ifdef __cplusplus
}
#endif
#endif
