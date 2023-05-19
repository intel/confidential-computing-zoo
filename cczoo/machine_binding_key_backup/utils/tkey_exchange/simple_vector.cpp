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

#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include "sgx_lfence.h"
#include "simple_vector.h"

//initial vector capacity when first item is added to vector
#define INIT_SIZE 10

//max vector capacity of a vector
#define MAX_SIZE 10000

//init vector to all zero
void vector_init(simple_vector* v)
{
    if (v)
    {
        v->size = 0;
        v->capacity = 0;
        v->data = NULL;
    }
}

//return current number of items the vector holds
uint32_t vector_size(const simple_vector* v)
{
    if (v)
        return v->size;
    else
        return 0;
}

//push a pointer to the end of the vector
//return 0 if success, return 1 if memory malloc failure.
errno_t vector_push_back(simple_vector* v, const void* data)
{
    if (v)
    {
        if (v->capacity == 0) {
            //first item
            v->data = (void**)malloc(sizeof(void*) * INIT_SIZE);
            if (v->data ==NULL)
                return 1;
            v->capacity = INIT_SIZE;
            memset(v->data, '\0', sizeof(void*) * INIT_SIZE);
        }
        else if (v->size == v->capacity) {
            void** new_data;
            if( v->capacity >= MAX_SIZE - INIT_SIZE)
                return 1;
            //increate size by INIT_SIZE
            new_data = (void**)realloc(v->data, sizeof(void*) *( v->capacity + INIT_SIZE));
            if (new_data ==NULL)
                return 1;
            memset(&new_data[v->capacity], '\0', sizeof(void*) * INIT_SIZE);
            v->data = new_data;
            v->capacity += INIT_SIZE;
        }
        //assign new item
        v->data[v->size] = const_cast<void*>(data);
        v->size++;
        return 0;
    }
    return 1;
}

//get the item pointer in the vector
//return 0 if success, return 1 if index is out of range or data pointer is invalid.
errno_t vector_get(const simple_vector* v, uint32_t index, void** data)
{
    if (!v || index >= v->size || !data)
        return 1;

    //fence after boundary check
    sgx_lfence();

    *data = v->data[index];
    return 0;
}

//set the pointer in the vector
//return 0 if success, return 1 if index is out of range.
errno_t vector_set(simple_vector* v, uint32_t index, const void* data)
{
    if (!v || index >= v->size)
        return 1;
    v->data[index] = const_cast<void*>(data);
    return 0;
}

//release memory used by the vector
void vector_free(simple_vector* v)
{
    if (v)
    {
        v->size = 0;
        v->capacity = 0;
        if(v->data)
        {
            free(v->data);
            v->data = NULL;
        }
    }
}
