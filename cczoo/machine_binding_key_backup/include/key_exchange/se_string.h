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

#ifndef _SE_STRING_H_ 
#define _SE_STRING_H_

#include "se_memcpy.h"
#include <string.h>


#ifndef _ERRNO_T_DEFINED
#define _ERRNO_T_DEFINED
typedef int errno_t;
#endif

static inline errno_t strcat_s(char *dst, size_t max_size, const char *src)
{
    if(strlen(dst)+strlen(src)+1>max_size)return -1;
    strcat(dst, src);
    return 0;
}

static inline errno_t strcpy_s(char *dst, size_t max_size, const char *src)
{
    if(strnlen(src, max_size)+1>max_size)return -1;
    strcpy(dst, src);
    return 0;
}

#define _strnicmp strncasecmp
static inline errno_t strncat_s(char *dst, size_t max_size, const char *src, size_t max_count)
{
    size_t len = strnlen(src,max_count);
    len+=strnlen(dst, max_size)+1;
    if(len>max_size)return -1;
    strncat(dst, src, max_count);
    return 0;
}

#define _strdup strdup
#define strnlen_s strnlen



#endif
