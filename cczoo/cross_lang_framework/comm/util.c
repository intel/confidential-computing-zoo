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

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "cross_comm.h"

const char* errcode2str(status_t c) {
	const char* s;
	switch(c) {
	case STATUS_SUCCESS: s="Success"; break;
	case STATUS_FAIL: s="Failed"; break;
	case STATUS_BAD_PARAM: s="Bad parameter"; break;
	case STATUS_OUT_OF_MEM: s="Out of memory"; break;
	case STATUS_NET_SEND_FAIL: s="net send fail"; break;
	default: s="N/A"; break;
	}
	return s;
}

void log_errcode(status_t c) {
	if(STATUS_SUCCESS == c) {
		printf("Result: %s\n", errcode2str(c));
	}
	else {
		printf("result: Failed, err_code: %X %s\n", c, errcode2str(c));
	}
}

#define MAX_LINE_LEN	1024
status_t read_config(const char* f, const char* key, char* val, int len, int *ret_len)
{
	status_t ret = STATUS_FAIL;

	if(!f || !key || !val)
		return STATUS_BAD_PARAM;

	FILE *fp = fopen(f, "r");
	if (fp == NULL)
		return STATUS_OPEN_FILE_FAIL;

	char line[MAX_LINE_LEN] = { 0 };
	while (!feof(fp))
	{
		memset(line, 0, MAX_LINE_LEN);
		char *s = fgets(line, MAX_LINE_LEN, fp);
		if (line[0] == '#' || !s)
		{
			continue;
		}

		char *pos = strchr(line, '=');
		if (pos == NULL)
		{
			continue;
		}

		char k[MAX_LINE_LEN] = { 0 };
		char v[MAX_LINE_LEN] = { 0 };

		strncpy(k, line, pos - line);
		strcpy(v, pos + 1);
		if (v[strlen(v) - 1] == '\n') {
			v[strlen(v) - 1] = 0;
		}

		if(strcmp(key, k) == 0) {
			if(strlen(v) > len-1) {
				if(ret_len)
					*ret_len = strlen(v)+1;
				goto out;
			}
			strncpy(val, v, len);
			ret = STATUS_SUCCESS;
			goto out;
		}
	}

out:
	return ret;
}

status_t read_config_int(const char* f, const char* key, int* val)
{
	status_t ret = STATUS_FAIL;
	char v[16] = { 0 };

	if(!f || !key || !val)
		return STATUS_BAD_PARAM;
	ret = read_config(f, key, v, 16, NULL);
	if(strlen(v)>0)
		*val = atoi(v);
	else
		*val = 0;

	return ret;
}

status_t read_config_short(const char* f, const char* key, int16_t* val)
{
	status_t ret = STATUS_FAIL;
	char v[16] = { 0 };

	if(!f || !key || !val)
		return STATUS_BAD_PARAM;
	ret = read_config(f, key, v, 16, NULL);
	*val = (int16_t)atoi(v);

	return ret;
}

void hexstr2buff(char* s, char* buff, int buf_len) {
	char b[3] = {0};
	int j = 0;
	uint32_t t = 0;

	if(!s || !buff || buf_len==0)
		return;
	if(strlen(s) == 0)
		return;

	for(int i = 0; i<strlen(s)-1 && j<buf_len; i+=2) {
		b[0] = s[i];
		b[1] = s[i+1];
		sscanf(b, "%x", &t);
		buff[j++] = *(char*)&t;
	}
}

void dump_buff(char *buff, int len) {
	if(!buff)
		return;

    for(int i = 0; i<len; ) {
        log_debug("%.2X", 0xff&buff[i]);
        i++;
        if(0==i%8) {
            log_debug("\n");
        } else {
            log_debug("-");
        }
    }
    log_debug("\n");
}

