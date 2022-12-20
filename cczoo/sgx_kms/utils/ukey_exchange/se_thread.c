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

#include "se_thread.h"
#include "se_types.h"

void se_mutex_init(se_mutex_t* mutex)
{
#ifdef PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP
    se_mutex_t tmp = PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP;
#elif defined(PTHREAD_RECURSIVE_MUTEX_INITIALIZER)
    se_mutex_t tmp = PTHREAD_RECURSIVE_MUTEX_INITIALIZER;
#else
#error no pre-defined RECURSIVE_MUTEX found.
#endif

    /* C doesn't allow `*mutex = PTHREAD_..._INITIALIZER'.*/
    memcpy(mutex, &tmp, sizeof(tmp));
}

int se_mutex_lock(se_mutex_t* mutex) { return (0 == pthread_mutex_lock(mutex)); }
int se_mutex_unlock(se_mutex_t* mutex) { return (0 == pthread_mutex_unlock(mutex)); }
int se_mutex_destroy(se_mutex_t* mutex) { return (0 == pthread_mutex_destroy(mutex));}

void se_thread_cond_init(se_cond_t* cond)
{
    se_cond_t tmp = PTHREAD_COND_INITIALIZER;
    memcpy(cond, &tmp, sizeof(tmp));
}

int se_thread_cond_wait(se_cond_t *cond, se_mutex_t *mutex){return (0 == pthread_cond_wait(cond, mutex));}
int se_thread_cond_signal(se_cond_t *cond){return (0 == pthread_cond_signal(cond));}
int se_thread_cond_broadcast(se_cond_t *cond){return (0 == pthread_cond_broadcast(cond));}
int se_thread_cond_destroy(se_cond_t* cond){return (0 == pthread_cond_destroy(cond));}

unsigned int se_get_threadid(void) { return (unsigned)syscall(__NR_gettid);}
/* tls functions */
int se_tls_alloc(se_tls_index_t *tls_index) { return !pthread_key_create(tls_index, NULL); }
int se_tls_free(se_tls_index_t tls_index) { return !pthread_key_delete(tls_index); }
void * se_tls_get_value(se_tls_index_t tls_index) { return pthread_getspecific(tls_index); }
int se_tls_set_value(se_tls_index_t tls_index, void *tls_value) { return !pthread_setspecific(tls_index, tls_value); }
/*
se_thread_handle_t se_create_thread(size_t stack_size, thread_start_routine_t start_routine, void *param, se_thread_t *thread)
{
	pthread_attr_t attr, *attr_ptr = NULL;
	int ret;

	if(stack_size > 0)
	{
		ret = pthread_attr_init(&attr);
		if(ret)
			return NULL;
		ret = pthread_attr_setstacksize(&attr, stack_size);
		if(ret)
			return NULL;
		attr_ptr = &attr;
	}
	else
	{
		attr_ptr = NULL;
	}
	ret = pthread_create(thread, attr_ptr, start_routine, param);
	if(ret)
		return NULL;
	if(attr_ptr)
		pthread_attr_destroy(&attr);

	return thread;

}
*/
