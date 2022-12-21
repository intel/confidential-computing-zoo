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

#include "rand.h"
#include "ecp.h"

uint32_t g_drng_feature = 0;

static void __cpuid(uint64_t cpu_info[4], uint64_t leaf, uint64_t subleaf)
{
    __asm__ __volatile__ (
        "cpuid;"
        : "=a" (cpu_info[0]),
        "=b" (cpu_info[1]),
        "=c" (cpu_info[2]),
        "=d" (cpu_info[3])
        : "a" (leaf), "c" (subleaf)
        : "cc"
    );
}

void get_drng_support(void)
{
    uint64_t info[4];

    __cpuid(info, 1, 0);
    if ((info[2] & 0x40000000) == 0x40000000) {
        g_drng_feature |= DRNG_HAS_RDRAND;
    }

    __cpuid(info, 7, 0);
    if ((info[1] & 0x40000) == 0x40000) {
        g_drng_feature |= DRNG_HAS_RDSEED;
    }
}

static int rdseed32(uint32_t *out)
{
    uint8_t ret;
    int i;

    for (i = 0; i < DRNG_MAX_TRIES; i++) {
        __asm__ __volatile__ (
            "RDSEED %0;"
            "setc %1;"
            : "=r"(*out), "=qm"(ret)
            );

        if (ret)
            return 0;
    }

    return -1;
}

static int rdrand32(uint32_t *out)
{
    uint8_t ret;
    int i;

    for (i = 0; i < DRNG_MAX_TRIES; i++) {
        __asm__ __volatile__ (
        "RDRAND %0;"
        "setc %1;"
        : "=r"(*out), "=qm"(ret)
        );

        if (ret)
            return 0;
    }

    return -1;
}

static int drng_rand32(uint32_t *out)
{
    int rc = -1;

    if (g_drng_feature & DRNG_HAS_RDSEED) {
        rc = rdseed32(out);
        if (0 == rc)
            return rc;
    }

    if (g_drng_feature & DRNG_HAS_RDRAND) {
        rc = rdrand32(out);
        if (0 != rc)
            printf("failed with rdrand32\n");
    }

    return rc;
}

int get_random(uint8_t *buf, size_t len)
{
    uint32_t i;

    if (len % 4) {
        printf("the len isn't multiple of 4bytes\n");
        return -1;
    }

    for (i = 0; i < len; i += 4) {
        uint32_t tmp_buf = 0;
        if (0 != drng_rand32(&tmp_buf)) {
            printf("failed with rdrng_rand32:%d.\n", i);
            return -1;
        }

    if (0 != memcpy_s(buf + i, sizeof(tmp_buf), &tmp_buf, sizeof(tmp_buf)))
        return -1;
    }

    return 0;
}

