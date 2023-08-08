/*
#
# Copyright (c) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
*/

#include <pthread.h>
#include <stdbool.h>
#include "/gramine/subprojects/cJSON-1.7.12/cJSON.h"

#define RA_TLS_MRS_MAX_SIZE 100
#define RA_TLS_CONFIG_JSON "./ra_config.json"

#define min(X,Y) ((X) < (Y) ? (X) : (Y))
#define max(X,Y) ((X) > (Y) ? (X) : (Y))

pthread_mutex_t g_print_lock;

struct ra_mr {
    char mr_enclave[32];
    char mr_signer[32];
    uint16_t isv_prod_id;
    uint16_t isv_svn;
};

struct ra_cfg {
    bool verify_mr_enclave;
    bool verify_mr_signer;
    bool verify_isv_prod_id;
    bool verify_isv_svn;
    int size;
    struct ra_mr mrs[RA_TLS_MRS_MAX_SIZE];
};

static struct ra_cfg cfg;

void hexdump_mem(const void* data, size_t size) {
    uint8_t* ptr = (uint8_t*)data;
    for (size_t i = 0; i < size; i++)
        printf("%02x", ptr[i]);
    printf("\n");
}

bool hex_to_byte(const char *src, char *dst, size_t dst_size) {
    if (strlen(src) < dst_size*2) {
        return false;
    } else {
        for (int i = 0; i < dst_size; i++) {
            if (!isxdigit(src[i*2]) || !isxdigit(src[i*2+1])) {
                return false;
            } else {
                sscanf(src+i*2, "%02hhx", dst+i);
            }
        }
        return true;
    }
};

void check_free(void* ptr) {
    if (ptr) {
        free(ptr);
        ptr = NULL;
    };
}

bool check_file(const char* file_path) {
    bool ret = false;
    if (file_path) {
        struct stat buffer;
        ret = stat(file_path, &buffer) == 0;
    }
    return ret;
}

void close_json_handle(cJSON* handle) {
    if (handle) {
        cJSON_Delete(handle);
        handle = NULL;
    }
};

cJSON* open_json_file(const char* file) {
    if (!file) {
        printf("wrong json file path\n");
        return false;
    }

    FILE *file_ptr = fopen(file, "r");
    fseek(file_ptr, 0, SEEK_END);
    int length = ftell(file_ptr);
    fseek(file_ptr, 0, SEEK_SET);
    char *buffer = malloc(length + 1); // +1 for a NULL
    size_t num_read = fread(buffer, 1, length, file_ptr);
    buffer[num_read] = '\0'; // terminate with NULL
    fclose(file_ptr);

    cJSON* handle = cJSON_Parse((const char *)buffer);

    check_free(buffer);

    if (!handle) {
        printf("cjson open %s error: %s", file, cJSON_GetErrorPtr());
    }
    return handle;
};

cJSON* get_item(cJSON* obj, const char* item) {
    return cJSON_GetObjectItem(obj, item);
};

char* print_item(cJSON* obj) {
    return cJSON_Print(obj);
};

bool cmp_item(cJSON* obj, const char* item) {
    char* obj_item = print_item(obj);
    return strncmp(obj_item+1, item, min(strlen(item), strlen(obj_item)-2)) == 0;
};

cJSON* parse_ra_config_json(const char* file) {
    if (!check_file(file)) {
        printf("could not to find and parse file!\n");
        return NULL;
    } else {
        cJSON* handle = open_json_file(file);
        printf("%s\n", print_item(handle));

        cfg.verify_mr_enclave = cmp_item(get_item(handle, "verify_mr_enclave"), "on");
        cfg.verify_mr_signer = cmp_item(get_item(handle, "verify_mr_signer"), "on");
        cfg.verify_isv_prod_id = cmp_item(get_item(handle, "verify_isv_prod_id"), "on");
        cfg.verify_isv_svn = cmp_item(get_item(handle, "verify_isv_svn"), "on");

        cJSON* objs = get_item(handle, "mrs");
        int obj_num = min(cJSON_GetArraySize(objs), RA_TLS_MRS_MAX_SIZE);

        cfg.size = 0;
        for (int i = 0; i < obj_num; i++) {
            cfg.size++;

            cJSON* obj = cJSON_GetArrayItem(objs, i);

            char* mr_enclave = print_item(get_item(obj, "mr_enclave"));
            memset(cfg.mrs[i].mr_enclave, 0, sizeof(cfg.mrs[i].mr_enclave));
            hex_to_byte(mr_enclave+1, cfg.mrs[i].mr_enclave, sizeof(cfg.mrs[i].mr_enclave));

            char* mr_signer = print_item(get_item(obj, "mr_signer"));
            memset(cfg.mrs[i].mr_signer, 0, sizeof(cfg.mrs[i].mr_signer));
            hex_to_byte(mr_signer+1, cfg.mrs[i].mr_signer, sizeof(cfg.mrs[i].mr_signer));

            char* isv_prod_id = print_item(get_item(obj, "isv_prod_id"));
            cfg.mrs[i].isv_prod_id = strtoul(isv_prod_id, NULL, 10);

            char* isv_svn = print_item(get_item(obj, "isv_svn"));
            cfg.mrs[i].isv_svn = strtoul(isv_svn, NULL, 10);
        };
        return handle;
    }
}

static bool verify_mr_internal(const char* mr_enclave,
                               const char* mr_signer,
                               const char* isv_prod_id,
                               const char* isv_svn) {
    bool status = false;
    if (!(cfg.verify_mr_enclave ||
        cfg.verify_mr_signer ||
        cfg.verify_isv_prod_id ||
        cfg.verify_isv_svn)) {
        status = true;
    } else {
        for (int i = 0; i < cfg.size; i++) {
            status = true;

            struct ra_mr obj = cfg.mrs[i];
            if (status && cfg.verify_mr_enclave && \
                memcmp(obj.mr_enclave, mr_enclave, 32)) {
                status = false;
            }

            if (status && cfg.verify_mr_signer && \
                memcmp(obj.mr_signer, mr_signer, 32)) {
                status = false;
            }

            if (status && cfg.verify_isv_prod_id && \
                (obj.isv_prod_id != *(uint16_t*)isv_prod_id)) {
                status = false;
            }

            if (status && cfg.verify_isv_svn && \
                (obj.isv_svn != *(uint16_t*)isv_svn)) {
                status = false;
            }

            if (status) {
                break;
            }
        }
    }
    return status;
}

/* our own callback to verify SGX ra_mrs during TLS handshake */
int verify_measurements_callback(const char* mr_enclave, const char* mr_signer,
                                 const char* isv_prod_id, const char* isv_svn) {
    bool status = false;
    pthread_mutex_lock(&g_print_lock);

    cJSON* handle = parse_ra_config_json(RA_TLS_CONFIG_JSON);
    if (!handle) {
        return -1;
    }

    assert(mr_enclave && mr_signer && isv_prod_id && isv_svn);
    status = verify_mr_internal(mr_enclave, mr_signer, isv_prod_id, isv_svn);
    printf("Received the following measurements from the client:\n");

    if (cfg.verify_mr_enclave) {
        printf("  |- MRENCLAVE      :  "); hexdump_mem(mr_enclave, 32);
    };

    if (cfg.verify_mr_signer) {
        printf("  |- MRSIGNER       :  "); hexdump_mem(mr_signer, 32);
    };

    if (cfg.verify_isv_prod_id) {
        printf("  |- ISV_PROD_ID    :  %hu\n", *((uint16_t*)isv_prod_id));
        };

    if (cfg.verify_isv_svn) {
        printf("  |- ISV_SVN        :  %hu\n", *((uint16_t*)isv_svn));
    };

    if (status) {
        printf("  |- Verify Result  :  success\n");
    } else {
        printf("  |- Verify Result  :  failed\n");
    }

    fflush(stdout);

    if (handle) {
        close_json_handle(handle);
    }
    pthread_mutex_unlock(&g_print_lock);
    return status ? 0 : -1;
}
