/* SPDX-License-Identifier: LGPL-3.0-or-later */
/* Copyright (C) 2020 Intel Labs */

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include "secret_prov.h"
#include "ra_server.h"

#define EXPECTED_STRING "MORE"
#define SECRET_STRING "42" /* answer to ultimate question of life, universe, and everything */

#define WRAP_KEY_FILENAME "files/wrap-key"
#define WRAP_KEY_SIZE     16

static pthread_mutex_t g_print_lock;
char g_secret_pf_key_hex[WRAP_KEY_SIZE * 2 + 1] = {0};

int communicate_with_client_callback(struct ra_tls_ctx* ctx);

static void hexdump_mem(const void* data, size_t size) {
    uint8_t* ptr = (uint8_t*)data;
    for (size_t i = 0; i < size; i++)
        printf("%02x", ptr[i]);
    printf("\n");
}

/* our own callback to verify SGX measurements during TLS handshake */
static int verify_measurements_callback(const char* mrenclave, const char* mrsigner,
                                        const char* isv_prod_id, const char* isv_svn) {
    assert(mrenclave && mrsigner && isv_prod_id && isv_svn);

    pthread_mutex_lock(&g_print_lock);
    puts("Received the following measurements from the client:");
    printf("  - MRENCLAVE:   "); hexdump_mem(mrenclave, 32);
    printf("  - MRSIGNER:    "); hexdump_mem(mrsigner, 32);
    printf("  - ISV_PROD_ID: %hu\n", *((uint16_t*)isv_prod_id));
    printf("  - ISV_SVN:     %hu\n", *((uint16_t*)isv_svn));
    puts("[ WARNING: In reality, you would want to compare against expected values! ]");
    pthread_mutex_unlock(&g_print_lock);

    return 0;
}

int main(int argc, char** argv) {
    int ret;

    ret = pthread_mutex_init(&g_print_lock, NULL);
    if (ret < 0)
        return ret;

    uint8_t ptr[16] = {0};
    for (size_t i = 0; i < 16; i++)
        sprintf(&g_secret_pf_key_hex[i * 2], "%02x", ptr[i]);

    puts("--- Starting the Secret Provisioning server on port 4433 ---");
    ret = secret_provision_start_server((uint8_t*)g_secret_pf_key_hex, sizeof(g_secret_pf_key_hex),
                                        "4433", "certs/server_signed_cert.crt", "certs/server_private_key.pem",
                                        verify_measurements_callback,
                                        communicate_with_client_callback);
    if (ret < 0) {
        fprintf(stderr, "[error] secret_provision_start_server() returned %d\n", ret);
        return 1;
    }

    pthread_mutex_destroy(&g_print_lock);
    return 0;
}
