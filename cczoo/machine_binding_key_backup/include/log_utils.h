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

#ifndef _LOG_UTILS_H
#define _LOG_UTILS_H

#include <stdio.h>
#include <stdarg.h>

#define IS_DEBUG false

/*
    print info
*/
#define log_i(format, args...)                                             \
    {                                                                      \
        printf("INFO [%s(%d) -> %s]: ", __FILE__, __LINE__, __FUNCTION__); \
        printf(format, ##args);                                            \
        printf("\n");                                                      \
    }
/*
    print debug
*/
#define log_d(format, args...)                                                  \
    {                                                                           \
        if (IS_DEBUG)                                                           \
        {                                                                       \
            printf("DEBUG [%s(%d) -> %s]: ", __FILE__, __LINE__, __FUNCTION__); \
            printf(format, ##args);                                             \
            printf("\n");                                                       \
        }                                                                       \
    }
/*
    print warn
*/
#define log_w(format, args...)                                             \
    {                                                                      \
        printf("WARN [%s(%d) -> %s]: ", __FILE__, __LINE__, __FUNCTION__); \
        printf(format, ##args);                                            \
        printf("\n");                                                      \
    }
/*
    print error
*/
#define log_e(format, args...)                                              \
    {                                                                       \
        printf("ERROR [%s(%d) -> %s]: ", __FILE__, __LINE__, __FUNCTION__); \
        printf(format, ##args);                                             \
        printf("\n");                                                       \
    }

#endif