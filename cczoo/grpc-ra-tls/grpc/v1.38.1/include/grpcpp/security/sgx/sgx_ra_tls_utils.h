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

#ifndef SGX_RA_TLS_UTILS_H
#define SGX_RA_TLS_UTILS_H

#include <string>
#include <vector>
#include <memory>
#include <dlfcn.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <time.h>
#include <sys/stat.h>

#include <grpcpp/security/sgx/sgx_ra_tls_log.h>

#define HEX_DUMP_SIZE   16
#define MAX_ROW_SIZE    70

namespace grpc {
namespace sgx {

#include <grpcpp/security/sgx/cJSON.h>

class library_engine {
    public:
        library_engine();

        library_engine(const char*, int);

        ~library_engine();

        void open(const char*, int);

        void close();

        void* get_func(const char*);

        void* get_handle();

    private:
        void* handle;
        char* error;
};

class json_engine {
    public:
        json_engine();

        json_engine(const char*);

        ~json_engine();

        bool open(const char*);

        void close();

        cJSON* get_handle();

        cJSON* get_item(cJSON* obj, const char* item);

        char* print_item(cJSON* obj);

        bool cmp_item(cJSON* obj, const char* item);

    private:
        cJSON* handle;
};

void check_free(void* ptr);

template<typename T>
void check_delete(T ptr);

bool check_file(const char* file_path);

bool hex_to_byte(const char* src, char* dst, size_t dst_size);

void byte_to_hex(const char* src, char* dst, size_t src_size);

std::string byte_to_hex(const char* src, size_t src_size);

void print_hex_dump(const char *title, const char *prefix_str,
                    const uint8_t *buf, int len);

} // namespace sgx
} // namespace grpc

#endif // SGX_RA_TLS_UTILS_H
