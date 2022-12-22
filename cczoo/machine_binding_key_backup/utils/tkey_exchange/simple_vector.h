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

#ifndef _SIMPLE_VECOTR_H
#define _SIMPLE_VECOTR_H

#include <stdint.h>

#ifdef  __cplusplus
extern "C" {
#endif

typedef struct _simple_vector
{
    uint32_t size;
    uint32_t capacity;
    void** data;
}simple_vector;

//call vector_init first or set all field to 0 to use a simple_vector
void vector_init(simple_vector* vector);

//get number of elements in simple_vector
uint32_t vector_size(const simple_vector* vector);

//insert an element to the end of simple_vector, the element can only be pointer
errno_t vector_push_back(simple_vector* vector, const void* data);

//get an element
errno_t vector_get(const simple_vector* v, uint32_t index, void** data);

//set an element content
errno_t vector_set(simple_vector* v, uint32_t index, const void* data);

//free the simple_vector allocated memory
void vector_free(simple_vector* vector);

#ifdef  __cplusplus
}
#endif

#endif
