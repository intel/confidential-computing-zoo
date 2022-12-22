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

#ifndef CACHECONTROLLER_H
#define CACHECONTROLLER_H

#include "sample_ra_msg.h"

#define CACHE_MAX_SESSION_NUM  16   // max sessionId number of cache
#define CACHE_DEAMON_SLEEP_TIME  60 * 5   // 5 minutes
#define CACHE_SP_DB_EXPIRED_TIME  60 * 5   // 5 minutes

/**
 * create a new sessionId and initialize a sp_db for this sessionId.Then return the sessonId
 * @param session_id_size
 * @return session_id
 */
int32_t db_initialize(sesion_id_t session_id);

/**
 * Destroy sp_db of sessionId and remove the sessionId from cache.
 * @param session_id
 * @return
 */
int32_t db_finalize(const sesion_id_t session_id);


/**
 * get a sp_db by sessionId.
 * @param session_id
 * @return p_sp_db
 */
int32_t get_session_db(const sesion_id_t session_id, sp_db_item_t **p_sp_db);

#endif //CACHECONTROLLER_H
