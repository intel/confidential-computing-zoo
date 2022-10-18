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

#include <stdlib.h>
#include <stdio.h>
#include <getopt.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>
#include <unistd.h>
#include <stdint.h>
#include <stdbool.h>
#include <dlfcn.h>

#include "cmd_params.h"
#include "cross_comm.h"

#define WRAP_KEY_SIZE	16
#define MRSIGNER_LEN	32
#define MRENCLAVE_LEN	32
#define PATH_MAX   1024
size_t strnlen_safe(const char *s, size_t maxlen)
{
	return !s ? 0 : strnlen(s, maxlen);
}

bool is_str_empty_or_too_long(const char *s, size_t maxlen)
{
	if (!s)
		return true;

	size_t n = strnlen_safe(s, maxlen + 1);
	if (n < 1 || n > maxlen)
		return true;
	else
		return false;
}

static void print_help(void)
{
	printf("Options:\n"
		   "-h/--help: print this help screen\n"
		   "-S/--MRSigner: the measurement value of signer\n"
		   "-d/--isv_prod_id: the ISV_PROD_ID of enclave\n"
		   "-v/--isv_svn: the ISV_SVN of enclave\n"
		   "-s/--secret: the key used to encrypt data\n"
		   "-p/--port: the port used in data/key transmission\n"
		   "-c/--server_cert_path: the path of secret cert\n"
		   "-k/--server_private_key_path: the path of private key\n");
}

static int validate_params(struct cmd_params *params)
{
	int err = 0;
	if (params == NULL)
		return 1;

	if (params->MRSigner[0] == 0 ) {
    
		printf("Error: -S/--MRSigner parameter missing\n");
		err = 1;
	}
	if (params->isv_prod_id == 65535) {
		printf("Error: -d/--isv_prod_id parameter missing\n");
		err = 1;
	}
	if (params->isv_svn == 65535) {
		printf("Error: -v/--isv_svn parameter missing\n");
		err = 1;
	}
	if (params->secret[0] == 0) {
		printf("Error: -s/--secret parameter missing\n");
		err = 1;
	}
	if (params->port[0] == 0) {
		printf("Error: -p/--port parameter missing\n");
		err = 1;
	}
	if (params->server_cert_path[0] == 0) {
		printf("Error: -c/--server_cert_path parameter missing\n");
		err = 1;
	}
	if (params->server_private_key_path[0] == 0) {
		printf("Error: -k/--server_private_key_path missing\n");
		err = 1;
	}
	return err;
}

int cmd_params_process(int argc, char **argv, struct cmd_params *params)
{
	const static char* _sopts = "h:S::E::d::v::s::p::c::k::";
	const static struct option _lopts[] = {{"help", no_argument, NULL, 'h'},
									{"MRSigner", required_argument, NULL, 'S'},
                  {"MREnclave", required_argument, NULL, 'E'},
									{"isv_prod_id", required_argument, NULL, 'd'},
									{"isv_svn", required_argument, NULL, 'v'},
									{"secret", required_argument, NULL, 's'},  
									{"port", required_argument, NULL, 'p'},
									{"server_cert_path", required_argument, NULL, 'c'},
									{"server_private_key_path", required_argument, NULL, 'k'},	  
									{0, 0, 0, 0}};
	int c;
	if (params == NULL)
		return 1;
	memset(params->MRSigner, 0, sizeof(params->MRSigner));
  memset(params->MREnclave, 0, sizeof(params->MREnclave));
	params->isv_prod_id = 65535;
	params->isv_svn = 65535;
	memset(params->secret, 0, sizeof(params->secret));
	memset(params->port, 0, sizeof(params->port));
	memset(params->server_cert_path, 0, sizeof(params->server_cert_path));
	memset(params->server_private_key_path, 0, sizeof(params->server_private_key_path));
	int len = 0;
	int tmp = 0;
	char szVal[PATH_MAX] = {0};
	const char conf[] = "clf_server.conf";
	while ((c = getopt_long(argc, argv, _sopts, _lopts, NULL)) != -1) {
		switch (c) {
		case 'h':
			print_help();
			return 1;
		case 'S':
			if (optarg == NULL || is_str_empty_or_too_long(optarg, 64)) {
			  if ( access(conf, 0) >= 0 ) {
					read_config(conf, "MRSigner", szVal, MRSIGNER_LEN, &len);
          printf("conf.MRSigner=%s\n", szVal);
					hexstr2buff(szVal, params->MRSigner, MRSIGNER_LEN);
					break;
				}
				printf("Error! MRSigner value invalid(empty or too long)!\n");
				return 1;
			}
			hexstr2buff(optarg, params->MRSigner, MRSIGNER_LEN);
			break;
    case 'E':
			if (optarg == NULL || is_str_empty_or_too_long(optarg, 64)) {
			  if ( access(conf, 0) >= 0 ) {
					read_config(conf, "MREnclave", szVal, MRSIGNER_LEN, &len);
          printf("conf.MREnclave=%s\n", szVal);
					hexstr2buff(szVal, params->MREnclave, MRSIGNER_LEN);
					break;
				}
			}
			hexstr2buff(optarg, params->MREnclave, MRSIGNER_LEN);
			break;
		case 'd':
			 if (optarg == NULL || is_str_empty_or_too_long(optarg, 6)) {
				if ( access(conf, 0) >= 0 ) {
					read_config_short(conf, "isv_prod_id", (int16_t*)&params->isv_prod_id);
					printf("conf.isv_prod_id=%d\n", params->isv_prod_id);
				break;
				}
				printf("Error! isv_prod_id value is invalid(empty)!\n");
				return 1;
			}
			strcpy(params->isv_prod_id , optarg);
			break;
		case 'v':
		 if (optarg == NULL || is_str_empty_or_too_long(optarg, 6)) {
				if ( access(conf, 0) >= 0  ) {
					read_config_short(conf, "isv_svn", (int16_t*)&params->isv_svn);	  
					printf("conf.isv_svn=%d\n", params->isv_svn);
					break;
				}
				printf("Error! isv_svn value is invalid(empty)!\n");
				return 1;
			}
			strcpy(params->isv_svn , optarg);
			break;
		case 's':
			if (optarg == NULL || is_str_empty_or_too_long(optarg, 32)) {
				if ( access(conf, 0) >= 0  ) {
					read_config(conf, "secret", szVal,	WRAP_KEY_SIZE, &len);
					printf("conf.secret=%s\n", szVal);
					strcpy(params->secret , szVal);
					break;
				}
				printf("Error! secret value is invalid(empty or too long)!\n");
				return 1;
			}
			printf("conf.secret=%s\n", optarg);
			strcpy(params->secret , optarg);
			break;
		case 'p':
			if (optarg == NULL) {
				if ( access(conf, 0) >= 0  ) {
					read_config(conf, "port", szVal, 8, &len);
					strcpy(params->port , szVal);
					printf("conf.port=%s\n", params->port);
					break;
				}
				printf("Error! port value is invalid!\n");
				return 1;
			}
			printf("conf.port=%s\n",optarg);
      if (atoi(optarg) > 65535) {
        printf("Error! port value is invalid!\n");
        return 1;
      }
			strcpy(params->port , optarg);
			break;
		case 'c':
			if (optarg == NULL || is_str_empty_or_too_long(optarg, PATH_MAX)) {
				if ( access(conf, 0) >= 0 ) {
					read_config(conf, "server_cert_path", szVal, PATH_MAX, &len);
					strcpy(params->server_cert_path , szVal);
					printf("conf.server_cert_path=%s\n",params->server_cert_path);
					break;
				}
				printf("Error! server_cert_path value is invalid!\n");
				return 1;
			}
			strcpy(params->server_cert_path , optarg);
			break;
		case 'k':
			if (optarg == NULL || is_str_empty_or_too_long(optarg, PATH_MAX)) {
				if ( access(conf, 0) >= 0  ) {
					read_config(conf, "server_private_key_path", szVal, PATH_MAX, &len);
					strcpy(params->server_private_key_path , szVal);
					printf("conf.server_private_key_path=%s",params->server_private_key_path);
					break;
				}
				printf("Error! server_private_key_path value invalid(empty or too long)!\n");
				return 1;
			}
			strcpy(params->server_private_key_path , optarg);
			break;
		default:
			printf("Error occurred during processing command-line options!\n");
			print_help();
			return 1;
		}
	}
	return validate_params(params);
}
