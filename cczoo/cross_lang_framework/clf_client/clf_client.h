#ifndef __CLS_CLIENT_h__
#define __CLS_CLIENT_h__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

int get_key(int8_t* key, int32_t key_len);
/* Java maximum array size is int32 */
int get_file_2_buff(char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len);
int get_file_size(char* fname, int64_t* ret_len);
int put_result(char* fname, int64_t offset, int8_t* data, int32_t len);

#ifdef __cplusplus
}
#endif
#endif
