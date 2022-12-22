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

#ifndef _SE_ARCH_H_
# error "never include inst.h directly; use arch.h instead."
#endif


#ifndef _SE_INST_H_
#define _SE_INST_H_

#define ENCLU 0xd7010f

typedef enum {
    SE_EREPORT = 0x0,
    SE_EGETKEY,
    SE_EENTER,
    SE_ERESUME,
    SE_EEXIT,
    SE_EACCEPT,
    SE_LAST_RING3,

    SE_ECREATE = 0x0,
    SE_EADD,
    SE_EINIT,
    SE_EREMOVE,
    SE_EDBGRD,
    SE_EDBGWR,
    SE_EEXTEND,
    SE_LAST_RING0
} se_opcode_t;

#endif
