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

/* This file implement lock guard */

#ifndef SE_LOCK_HPP
#define SE_LOCK_HPP

#include "util.h"
#include "se_thread.h"
#include "uncopyable.h"

class Mutex: private Uncopyable
{
public:
    Mutex(){se_mutex_init(&m_mutex);}
    ~Mutex(){se_mutex_destroy(&m_mutex);}
    void lock(){se_mutex_lock(&m_mutex);}
    void unlock(){se_mutex_unlock(&m_mutex);}
private:
    se_mutex_t m_mutex;
};

class Cond: private Uncopyable
{
public:
    Cond(){se_mutex_init(&m_mutex); se_thread_cond_init(&m_cond);}
    ~Cond(){se_mutex_destroy(&m_mutex); se_thread_cond_destroy(&m_cond);}
    void lock(){se_mutex_lock(&m_mutex);}
    void unlock(){se_mutex_unlock(&m_mutex);}
    void wait(){se_thread_cond_wait(&m_cond, &m_mutex);}
    void signal(){se_thread_cond_signal(&m_cond);}
    void broadcast(){se_thread_cond_broadcast(&m_cond);}
private:
    se_mutex_t m_mutex;
    se_cond_t  m_cond;
};

class LockGuard: private Uncopyable
{
public:
    LockGuard(Mutex* mutex):m_mutex(mutex){m_mutex->lock();}
    ~LockGuard(){m_mutex->unlock();}
private:
    Mutex* m_mutex;
};

#endif
