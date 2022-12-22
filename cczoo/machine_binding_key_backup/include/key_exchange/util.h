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

#ifndef _UTIL_H_
#define _UTIL_H_

#include "arch.h"
#include <assert.h>

#ifdef __cplusplus
#define	GET_PTR(t, p, offset) reinterpret_cast<t*>( reinterpret_cast<size_t>(p) + static_cast<size_t>(offset) )
#define PTR_DIFF(p1, p2)	((reinterpret_cast<size_t>(p1) - reinterpret_cast<size_t>(p2)))
#else
#define	GET_PTR(t, p, offset) (t*)( (size_t)(p) + (size_t)(offset) )
#define PTR_DIFF(p1, p2)	((size_t)(p1) - (size_t)(p2))
#endif

#define DIFF(p1, p2)        (assert((size_t)(p1) >= (size_t)(p2)), ((size_t)(p1) - (size_t)(p2)))
#define DIFF64(p1, p2)      (assert((uint64_t)(p1) >= (uint64_t)(p2)), ((uint64_t)(p1) - (uint64_t)(p2)))

#define SE_PAGE_SHIFT       12
#define SE_BULK_PAGE_FRAME_SHIFT 4
#define SE_BULK_PAGE_FRAME_SIZE (1 << SE_BULK_PAGE_FRAME_SHIFT)
#define SE_BULK_PAGE_FRAME_MASK (SE_BULK_PAGE_FRAME_SIZE-1)
#define SE_BULK_PAGE_SHIFT	(SE_PAGE_SHIFT + SE_BULK_PAGE_FRAME_SHIFT)
#define SE_BULK_PAGE_SIZE	(1 << SE_BULK_PAGE_SHIFT)
#define SE_GUARD_PAGE_SHIFT 16
#define SE_GUARD_PAGE_SIZE (1 << SE_GUARD_PAGE_SHIFT)

#define	ROUND_TO(x, align)  (((x) + ((align)-1)) & ~((align)-1))
#define	ROUND_TO_PAGE(x)    ROUND_TO(x, SE_PAGE_SIZE)
#define	TRIM_TO_PAGE(x) ((x) & ~(SE_PAGE_SIZE-1))
#define PAGE_OFFSET(x) ((x) & (SE_PAGE_SIZE -1))
#ifdef __cplusplus
#define PAGE_ALIGN(t, x)	reinterpret_cast<t*>((reinterpret_cast<size_t>(x)+(SE_PAGE_SIZE-1)) & (~(SE_PAGE_SIZE-1)))
#else
#define PAGE_ALIGN(t, x)	(t*)( ((size_t)(x)+(SE_PAGE_SIZE-1)) & (~(SE_PAGE_SIZE-1)) )
#endif

#define IS_PAGE_ALIGNED(x)	(!((size_t)(x)&(SE_PAGE_SIZE-1)))

#define MIN(x, y) (((x)>(y))?(y):(x))
#define MAX(x, y) (((x)>(y))?(x):(y))
#define ARRAY_LENGTH(x) (sizeof(x)/sizeof(x[0]))

/* used to eliminate `unused variable' warning */
#define UNUSED(val) (void)(val)

#include <stddef.h>
#define container_of(ptr, type, member) (type *)( (char *)(ptr) - offsetof(type,member) )

#ifndef weak_alias
#define weak_alias(_old, _new) __typeof(_old) _new __attribute__((weak, alias(#_old)))
#endif

#endif
