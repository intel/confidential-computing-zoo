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

#ifndef _SE_CDEFS_H_
#define _SE_CDEFS_H_


#define SGX_WEAK __attribute__((weak))

# if (__GNUC__ >= 3)
#  define likely(x)	__builtin_expect ((x), 1)
#  define unlikely(x)	__builtin_expect ((x), 0)
# else
#  define likely(x)	(x)
#  define unlikely(x)	(x)
# endif

#ifndef SE_DECLSPEC_EXPORT
#define SE_DECLSPEC_EXPORT __attribute__((visibility("default")))
#endif

#ifndef SE_DECLSPEC_IMPORT
#define SE_DECLSPEC_IMPORT
#endif

#ifndef SE_DECLSPEC_ALIGN
#define SE_DECLSPEC_ALIGN(x) __attribute__((aligned(x)))
#endif

#ifndef SE_DECLSPEC_THREAD
#define SE_DECLSPEC_THREAD /*__thread*/
#endif

/* disable __try, __except on linux */
#ifndef __try
#define __try try
#endif

#ifndef __except
#define __except(x) catch(...)
#endif


#ifndef SE_DRIVER

#	define SE_GNU
#	if defined(__x86_64__)
#		define SE_64
#		define SE_GNU64
#	else
#		define SE_32
#		define SE_GNU32
#	endif

#endif

	#define INITIALIZER(f) \
	static void f(void) __attribute__((constructor));

#ifdef __cplusplus
#define MY_EXTERN extern "C"
#else
#define MY_EXTERN extern
#endif

#define SGX_ACCESS_VERSION(libname, num)                    \
    MY_EXTERN char sgx_##libname##_version[];          \
    MY_EXTERN char * __attribute__((destructor)) libname##_access_version_dummy##num()      \
    {                                                                                       \
        sgx_##libname##_version[0] = 's';                                                   \
        return sgx_##libname##_version;                                                     \
    } 


#endif
