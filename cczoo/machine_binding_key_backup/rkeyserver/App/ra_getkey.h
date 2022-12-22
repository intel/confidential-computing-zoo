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

#ifndef _RA_GETKEY_H_
#define _RA_GETKEY_H_

#include <cstdint>
#include <vector>
#include <memory>
#include "datatypes.h"
#include "sample_ra_msg.h"

using namespace std;

namespace ra_getkey {

int32_t Initialize_ra(std::string deploy_ip_addr, uint32_t deploy_port);

}

#endif
