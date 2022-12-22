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

#ifndef SE_STDIO_H
#define SE_STDIO_H

#include <stdio.h>
#include <stddef.h>
#include "se_memcpy.h"
#include <stdarg.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>

#ifndef MAX_PATH
#define MAX_PATH 260
#endif

static inline int se_delete_file(const char *path_name)
{
    return unlink(path_name);
}

#define se_delete_tfile se_delete_file

static inline int sprintf_s(char *dst_buf, size_t size_in_bytes, const char *format, ...)
{
    va_list argptr;
    int cnt;
    va_start(argptr, format);
    cnt = vsnprintf(dst_buf, size_in_bytes, format, argptr);
    va_end(argptr);
    return cnt;
}

static inline int _snprintf_s(char *dst_buf, size_t size_in_bytes, size_t max_count, const char *format, ...)
{
    (void) size_in_bytes;
    va_list argptr;
    int cnt;
    va_start(argptr, format);
    cnt = vsnprintf(dst_buf, max_count, format, argptr);
    va_end(argptr);
    return cnt;
}

static inline errno_t fopen_s(FILE **f, const char *filename, const char *mode)
{
    errno_t err = 0;
    *f = fopen(filename, mode);
    if(*f==NULL){
        err = -1;
    }
    return err;
}

static inline int se_copy_file(const char *dst_name, const char *src_name)
{
    int dest = -1;
    int source = -1;
    ssize_t nr_read;
    struct stat stat_buf;

#ifndef BUF_SIZE
#define BUF_SIZE 4096
#endif
    char buf[BUF_SIZE];

    /* open the input file */
    source = open(src_name, O_RDONLY);
    if(source < 0)
        goto error;

    /* get size and permissions of the prebuild DB file */
    if (fstat(source, &stat_buf) != 0)
        goto error;

    dest = open(dst_name, O_WRONLY|O_CREAT|O_TRUNC, stat_buf.st_mode); 
    if(dest < 0)
        goto error;

    while ((nr_read = read(source, buf, BUF_SIZE)) > 0)
    {
        if (write(dest, buf, nr_read) != nr_read)
            goto error;
    }
#undef BUF_SIZE

    close(dest);
    close(source);
    return 0;

error:
    if(dest>=0)close(dest);
    if(source>=0)close(source);
    return -1;
}

#ifdef __cplusplus
template <size_t _Size>
int sprintf_s(char (&dst)[_Size], const char *format, ...)
{
    va_list argptr;
    int cnt;
    va_start(argptr, format);
    cnt = vsprintf(dst, format, argptr);
    va_end(argptr);
    return cnt;
}

template<size_t _Size>
int _snprintf_s(char (&dst)[_Size], size_t max_count, const char *format, ...)
{
    va_list argptr;
    int cnt;
    va_start(argptr, format);
    cnt = vsnprintf(dst, max_count, format, argptr);
    va_end(argptr);
    return cnt;
}

#endif

#endif
