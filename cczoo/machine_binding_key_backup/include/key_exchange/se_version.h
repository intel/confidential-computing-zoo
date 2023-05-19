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

#ifndef _SE_VERSION_H_
#define _SE_VERSION_H_

#define STRFILEVER    "2.15.101.1"
#define SGX_MAJOR_VERSION       2
#define SGX_MINOR_VERSION       15
#define SGX_REVISION_VERSION    101
#define MAKE_VERSION_UINT(major,minor,rev)  (((uint64_t)major)<<32 | ((uint64_t)minor) << 16 | rev)
#define VERSION_UINT        MAKE_VERSION_UINT(SGX_MAJOR_VERSION, SGX_MINOR_VERSION, SGX_REVISION_VERSION)

#define COPYRIGHT      "Copyright (C) 2021 Intel Corporation"

#define UAE_SERVICE_VERSION       "2.3.213.1"
#define URTS_VERSION              "1.1.117.1"
#define ENCLAVE_COMMON_VERSION    "1.1.120.1"
#define LAUNCH_VERSION            "1.0.115.1"
#define EPID_VERSION              "1.0.115.1"
#define QUOTE_EX_VERSION          "1.1.115.1"

#endif
