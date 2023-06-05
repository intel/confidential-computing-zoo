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

#include "CacheController.h"

#include <cstring>
#include <string>
#include <map>
#include <sys/time.h>

#include "error.h"
#include "rand.h"
#include "log_utils.h"
#include "socket_server.h"


static std::map<std::string, sp_db_item_t *> g_session_db_map;

pthread_t pthread_clean_expired;

void *thread_clean_expired_sessionDB(void *unused) {
    log_d("thread_clean_expired_sessionDB start");
    while (true) {
        sleep(CACHE_DEAMON_SLEEP_TIME);// 5 minutes
        // get current time
        struct timeval tv;
        gettimeofday(&tv, NULL);
        long current_time = tv.tv_sec;
        std::map<std::string, sp_db_item_t *>::reverse_iterator iter;
        for (iter = g_session_db_map.rbegin(); iter != g_session_db_map.rend(); iter++) {
            if (iter->second->expired_time < current_time) {
                std::string sessionId = iter->first;
                db_finalize((uint8_t *) sessionId.c_str());
            }
            if (g_session_db_map.size() == 0) {
                // After executing db_finalize, if g_session_db_map's size is 0, [iter++] will make an error, So we need to quit voluntarily.
                break;
            }
        }
    }
    log_d("thread_clean_expired_sessionDB end");
}

/**
 * create a new sessionId and initialize a sp_db for this sessionId.Then return the sessonId
 * @return session_id
 */
int32_t db_initialize(sesion_id_t session_id) {
    log_d("start db_initialize.");
    uint32_t ret = NO_ERROR;

    if (session_id == NULL) {
        return SP_INTEGRITY_FAILED;
    }

    // generate sessionId
    std::string psw_chars = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz";
    uint8_t temp[SESSION_ID_SIZE];
    get_drng_support();// initialize for get_random
    if (0 != get_random(temp, SESSION_ID_SIZE)) {
        log_e("failed to get random.");
        return SP_INTERNAL_ERROR;
    }
    for (int i = 0; i < SESSION_ID_SIZE; i++) {
        session_id[i] = psw_chars[temp[i] % psw_chars.length()];
    }

    // create a new sp_db_item_t for the sessionId
    sp_db_item_t *p_sp_db;
    p_sp_db = (sp_db_item_t *) malloc(sizeof(sp_db_item_t));
    if (p_sp_db == NULL) {
        log_e("sp_db malloc exception.");
        return SP_INTERNAL_ERROR;
    }
    memcpy_s(p_sp_db->session_id, SESSION_ID_SIZE, session_id, SESSION_ID_SIZE);
    struct timeval tv;
    gettimeofday(&tv, NULL);
    p_sp_db->expired_time = tv.tv_sec + CACHE_SP_DB_EXPIRED_TIME;// The expiration time is 5 minutes after creation.
    log_d("create p_sp_db success.");

    // insert session_id->p_sp_db to Map
    std::string key((char *) session_id, SESSION_ID_SIZE);
    if (g_session_db_map.size() < CACHE_MAX_SESSION_NUM) {
        g_session_db_map.insert(std::make_pair(key, p_sp_db));
        log_d("insert session_id->p_sp_db to Map success.");
    } else {
        log_e("DB maximum capacity reached.The max session is 16, current[%ld]", g_session_db_map.size());
        return SP_INTERNAL_ERROR;
    }

    // start a thread_clean_expired_sessionDB
    if (pthread_clean_expired == NULL) {
        pthread_create(&pthread_clean_expired, NULL, thread_clean_expired_sessionDB, NULL);
    }

    log_d("end db_initialize.");
    return ret;
}

/**
 * Destroy sp_db of sessionId and remove the sessionId from cache.
 * @param session_id
 * @return
 */
int32_t db_finalize(const sesion_id_t session_id) {
    log_d("start db_finalize. sessionId: %s", session_id);
    uint32_t ret = NO_ERROR;
    if (!session_id) {
        return SP_INTEGRITY_FAILED;
    }

    std::string key((char *) session_id, SESSION_ID_SIZE);
    std::map<std::string, sp_db_item_t *>::iterator iter;
    iter = g_session_db_map.find(key);
    if (iter != g_session_db_map.end()) {
        // find spdb
        sp_db_item_t *p_sp_db;
        p_sp_db = iter->second;

        // set pp_sp_db to zero
        explicit_bzero(p_sp_db, sizeof(sp_db_item_t));
        SAFE_FREE(p_sp_db);

        // remove the session db from g_session_db_map
        g_session_db_map.erase(key);
        log_d("finalize sp_db success! current size[%ld].", g_session_db_map.size());
    } else {
        log_d("find sp_db failed!");
    }

    log_d("end db_finalize.");
    return ret;
}


/**
 * get a sp_db by sessionId.
 * @param session_id
 * @return p_sp_db
 */
int32_t get_session_db(const sesion_id_t session_id, sp_db_item_t **pp_sp_db) {
    log_d("start get_session_db.");
    uint32_t ret = NO_ERROR;
    if (!session_id || !pp_sp_db) {
        return SP_INTEGRITY_FAILED;
    }
    std::string key((char *) session_id, SESSION_ID_SIZE);
    log_d("key is [%s]", key.c_str());
    std::map<std::string, sp_db_item_t *>::iterator iter;
    iter = g_session_db_map.find(key);
    if (iter != g_session_db_map.end()) {
        *pp_sp_db = iter->second;
        log_d("find sp_db success!");
    } else {
        *pp_sp_db = NULL;
        log_d("find sp_db failed!");
    }
    log_d("end get_session_db.");
    return ret;
}
