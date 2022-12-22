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

#ifndef _SE_THREAD_H_
#define _SE_THREAD_H_


#ifndef _GNU_SOURCE
#define _GNU_SOURCE /* for PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP */
#endif
#include <string.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <pthread.h>
typedef pthread_mutex_t se_mutex_t;
typedef pthread_cond_t se_cond_t;
typedef pid_t se_thread_id_t;
typedef pthread_key_t se_tls_index_t;

#ifdef __cplusplus
extern "C" {
#endif
/*
@mutex:	A pointer to the critical section object.
@return value:	If the function succeeds, the return value is nonzero.If the function fails, the return value is zero.
*/
void se_mutex_init(se_mutex_t* mutex);
int se_mutex_lock(se_mutex_t* mutex);
int se_mutex_unlock(se_mutex_t* mutex);
int se_mutex_destroy(se_mutex_t* mutex);

void se_thread_cond_init(se_cond_t* cond);
int se_thread_cond_wait(se_cond_t *cond, se_mutex_t *mutex);
int se_thread_cond_signal(se_cond_t *cond);
int se_thread_cond_broadcast(se_cond_t *cond);
int se_thread_cond_destroy(se_cond_t* cond);

unsigned int se_get_threadid(void);

/* tls functions */
int se_tls_alloc(se_tls_index_t *tls_index);
int se_tls_free(se_tls_index_t tls_index);
void * se_tls_get_value(se_tls_index_t tls_index);
int se_tls_set_value(se_tls_index_t tls_index, void *tls_value);

/* se_thread_handle_t se_create_thread(size_t stack_size, thread_start_routine_t start_routine, void *param, se_thread_t* thread); */

#ifdef __cplusplus
}
#endif

#endif
