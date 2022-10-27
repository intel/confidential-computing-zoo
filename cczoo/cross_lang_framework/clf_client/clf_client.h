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

#ifndef __CLS_CLIENT_h__
#define __CLS_CLIENT_h__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LOCAL_FS	"local"

/* the common API exposed to upper layer, e.g. JNI */
int get_key(int8_t* ip_port, int8_t* ca_cert, int8_t* key, int32_t key_len);
int get_file_size(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t* ret_len);
/* Java maximum array size is int32 */
int get_file_2_buff(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len);
int put_result(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len);

/* the series of API that targeting local filesystem */
int local_get_file_size(char* fname, int64_t* ret_len);
int local_get_file_2_buff(char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len);
int local_put_result(char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len);

/* the series of API that targeting remote clf_server */
int remote_get_file_size(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t* ret_len);
int remote_get_file_2_buff(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len);
int remote_put_result(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len);

#ifdef __cplusplus
}
#endif
#endif
