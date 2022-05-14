#ifndef __CROSS_COMM_h__
#define __CROSS_COMM_h__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
	MSG_FIRST = 0x2022A000,
	MSG_GET_DATA,
	MSG_GET_DATA_SIZE,
	MSG_PUT_RESULT,
	MSG_LAST
} msg_type_t;

#define MAX_FNAME_LEN	4096		//PATH_MAX

typedef enum {
	STATUS_SUCCESS			= 0,
	STATUS_FAIL				= 0x20221000,
	STATUS_BAD_PARAM		= 0x20221001,
	STATUS_OUT_OF_MEM		= 0x20221002,
	STATUS_NET_SEND_FAIL	= 0x20221003
} status_t;

typedef struct _msg_req_t {
	msg_type_t msg_type;
	uint32_t reserve1;
	uint64_t data_len;
	union {
		struct {
			uint64_t offset;
			uint64_t len;
			int8_t fname[MAX_FNAME_LEN];
		} get_data;
		struct {
			int8_t fname[MAX_FNAME_LEN];
		} get_size;
		struct {
			uint64_t offset;
			uint64_t len;
			int8_t fname[MAX_FNAME_LEN];
		} put_res;
	};
	uint8_t data[0];
} msg_req_t;

typedef struct _msg_resp_t {
	uint32_t status;
	uint32_t reserve1;
	union {
		struct {
			uint64_t data_len;
		} get_data;
		struct {
			uint64_t len;
		} get_size;
		struct {
			uint64_t received_len;
		} put_res;
	};
	uint8_t data[0];
} msg_resp_t;

#define log_error(fmt, ...)                      \
    do {                                         \
            fprintf(stderr, fmt, ##__VA_ARGS__); \
    } while (0)

#define log_debug(fmt, ...)                      \
    do {                                         \
            fprintf(stderr, fmt, ##__VA_ARGS__); \
    } while (0)

#ifdef __cplusplus
}
#endif
#endif
