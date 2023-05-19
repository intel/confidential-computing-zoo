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
	STATUS_NET_SEND_FAIL	= 0x20221003,
	STATUS_OPEN_FILE_FAIL	= 0x20221004
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

typedef enum {
	LOG_LEVEL_DEBUG = 1,
	LOG_LEVEL_INFO = 2,
	LOG_LEVEL_ERROR = 3
} log_level_t;

extern log_level_t g_log_level;

#define log_error(fmt, ...)                      \
    do {                                         \
        if(g_log_level<=LOG_LEVEL_ERROR)fprintf(stderr, fmt, ##__VA_ARGS__); \
    } while (0)

#define log_info(fmt, ...)                       \
    do {                                         \
        if(g_log_level<=LOG_LEVEL_INFO)fprintf(stderr, fmt, ##__VA_ARGS__); \
    } while (0)

#define log_debug(fmt, ...)                      \
    do {                                         \
        if(g_log_level<=LOG_LEVEL_DEBUG)fprintf(stderr, fmt, ##__VA_ARGS__); \
    } while (0)

void log_errcode(status_t c);
status_t read_config(const char* f, const char* key, char* val, int len, int *ret_len);
status_t read_config_int(const char* f, const char* key, int* val);
status_t read_config_short(const char* f, const char* key, int16_t* val);
void hexstr2buff(char* s, char* buff, int buf_len);
void dump_buff(char *buff, int len);

int64_t fileread(char* f, uint64_t offset, int8_t* buf, uint64_t len);
int64_t filesize(char* f);
int64_t filewrite(char* f, uint64_t offset, int8_t* buf, uint64_t len);

#ifdef __cplusplus
}
#endif
#endif
