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

#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <stdarg.h>
#include "secret_prov.h"
#include "cross_comm.h"

#define SEND_STRING "MORE"


int test_secret_prov_connect() {
    int ret;

    struct ra_tls_ctx* ctx = NULL;

    bool is_constructor = false;
    char* str = getenv(SECRET_PROVISION_CONSTRUCTOR);
    if (str && (!strcmp(str, "1") || !strcmp(str, "true") || !strcmp(str, "TRUE")))
        is_constructor = true;

    if (!is_constructor) {
        /* secret provisioning was not run as part of initialization, run it now */
        ret = secret_provision_start("VM-0-3-ubuntu:4433",
                                     "certs/ca_cert.crt", &ctx);
        if (ret < 0) {
            log_error("[error] secret_provision_start() returned %d\n", ret);
            goto out;
        }
    }

    ret = 0;
out:
    secret_provision_close(ctx);
    return ret;
}

static int list_dir(char *path) {
    DIR *d;
    struct dirent *dir;
	printf("------list_dir IN------\n");
	log_error("------list_dir IN: %s------\n", path);
    d = opendir(path);
    if (d) {
        while ((dir = readdir(d)) != NULL) {
			log_error("%s\n", dir->d_name);
        	printf("%s\n", dir->d_name);
        }
    }
    closedir(d);
	printf("------list_dir OUT------\n");
	log_error("------list_dir OUT------\n");
	return 0;
}

int secret_prov_test() {
	return 0;
}

