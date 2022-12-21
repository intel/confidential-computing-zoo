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

/*
 *	This file is to define some types that is platform independent.
*/

#ifndef _SE_TYPE_H_
#define _SE_TYPE_H_
#include "se_cdefs.h"

#ifdef SE_DRIVER

typedef	INT8	int8_t;
typedef	UINT8	uint8_t;
typedef	INT16	int16_t;
typedef	UINT16	uint16_t;
typedef	INT32	int32_t;
typedef	UINT32	uint32_t;
typedef	INT64	int64_t;
typedef	UINT64	uint64_t;

#else

#include <stdint.h>
#include <unistd.h>

#ifndef TRUE
#define	TRUE 1
#endif

#ifndef FALSE
#define FALSE 0
#endif

#endif

#if defined(SE_64)

#define	PADDED_POINTER(t, p)        t* p
#define	PADDED_DWORD(d)             uint64_t d
#define	PADDED_LONG(l)              int64_t l
#define REG(name)                   r##name
#ifdef SE_SIM_EXCEPTION
#define REG_ALIAS(name)             R##name
#endif
#define REGISTER(name)              uint64_t REG(name)

#else /* !defined(SE_64) */

#define	PADDED_POINTER(t, p) t* p;  void*    ___##p##_pad_to64_bit
#define	PADDED_DWORD(d)             uint32_t d; uint32_t ___##d##_pad_to64_bit
#define	PADDED_LONG(l)              int32_t l;  int32_t  ___##l##_pad_to64_bit

#define REG(name)                   e##name

#ifdef SE_SIM_EXCEPTION
#define REG_ALIAS(name)             E##name
#endif

#define REGISTER(name)              uint32_t REG(name); uint32_t ___##e##name##_pad_to64_bit

#endif /* !defined(SE_64) */

#endif
