#ifndef __CLF_SERVER_h__
#define __CLF_SERVER_h__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

uint64_t fileread(int8_t* f, uint64_t offset, uint8_t* buf, uint64_t len);
int64_t get_file_size(char* f);
uint64_t filewrite(int8_t* f, uint64_t offset, uint8_t* buf, uint64_t len);

#ifdef __cplusplus
}
#endif
#endif
