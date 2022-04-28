#ifndef __CLS_CLIENT_h__
#define __CLS_CLIENT_h__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

int get_key(int8_t* ip_port, int8_t* ca_cert, int8_t* key, int32_t key_len);
int get_file_size(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t* ret_len);
/* Java maximum array size is int32 */
int get_file_2_buff(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len);
int put_result(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len);


void dump_buff(char *buff, int len);

#ifdef __cplusplus
}
#endif
#endif
