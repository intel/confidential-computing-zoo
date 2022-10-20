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


bool is_str_length_invalid(const char *s, size_t size)
{
	if (s && strlen(s) != size)
		return true;
	else
		return false;
}

static void print_help(void)
{
	printf("Options:\n"
		   "-h/--help: print this help\n"
		   "-S/--MRSigner: the measurement value of signer\n"
		   "-d/--isv_prod_id: the ISV_PROD_ID of enclave\n"
		   "-v/--isv_svn: the ISV_SVN of enclave\n"
		   "-s/--secret: the secret used to encrypt data\n"
		   "-p/--port: the network port that clf_server binding\n"
		   "-c/--server_cert_path: the path of certification\n"
		   "-k/--server_private_key_path: the path of private key\n");
}

static int load_from_conf_file_if_missing(struct cmd_params *params)
{
	char szVal[PATH_MAX] = {0};
	const char conf[] = "clf_server.conf";
	int err = 0;
	int len;

	if (params == NULL)
		return -1;

	if (params->MRSigner[0] == 0 ) {
		if ( access(conf, 0) >= 0 ) {
			read_config(conf, "MRSigner", szVal, MRSIGNER_LEN*2+1, &len);
			printf("conf.MRSigner=%s\n", szVal);
			hexstr2buff(szVal, params->MRSigner, MRSIGNER_LEN);
		}
		if (params->MRSigner[0] == 0 ) {
			printf("Attention: -S/--MRSigner parameter is not specified, will ignore checking MRSigner in remote attestation\n");
		}
	}
	if (params->MREnclave[0] == 0 ) {
		if ( access(conf, 0) >= 0 ) {
			read_config(conf, "MREnclave", szVal, MRSIGNER_LEN*2+1, &len);
			printf("conf.MREnclave=%s\n", szVal);
			hexstr2buff(szVal, params->MREnclave, MRSIGNER_LEN);
		}
		if (params->MREnclave[0] == 0 ) {
			printf("Attention: -S/--MREnclave parameter is not specified, will ignore checking MREnclave in remote attestation\n");
		}
	}
	if (params->isv_prod_id == 0xFFFF) {
		if ( access(conf, 0) >= 0 ) {
			read_config_short(conf, "isv_prod_id", (int16_t*)&params->isv_prod_id);
			printf("conf.isv_prod_id=%d\n", params->isv_prod_id);
		} else {
			params->isv_prod_id = 0;
			printf("Attention: -d/--isv_prod_id parameter is not specified, default set to 0\n");
		}
	}
	if (params->isv_svn == 0xFFFF) {
		if ( access(conf, 0) >= 0  ) {
			read_config_short(conf, "isv_svn", (int16_t*)&params->isv_svn);
			printf("conf.isv_svn=%d\n", params->isv_svn);
		} else {
			params->isv_svn = 0;
			printf("Attention: -v/--isv_svn parameter is not specified, default set to 0\n");
		}
	}
	if (params->secret[0] == 0) {
		if ( access(conf, 0) >= 0  ) {
			read_config(conf, "secret", szVal, WRAP_KEY_SIZE*2+1, &len);
			printf("conf.secret=%s\n", szVal);
			strcpy(params->secret, szVal);
		}
		if (params->secret[0] == 0 ) {
			printf("Error: -s/--secret parameter missing\n");
			err = -1;
		}
	}
	if (params->port == 0xFFFF) {
		if ( access(conf, 0) >= 0  ) {
			read_config_short(conf, "port", (int16_t*)&params->port);
			printf("conf.port=%d\n", params->port);
		} else {
			params->port = 4433;
			printf("Attention: -p/--port parameter missing, default set to 4433\n");
		}
	}
	if (params->server_cert_path[0] == 0) {
		if ( access(conf, 0) >= 0 ) {
			read_config(conf, "server_cert_path", szVal, PATH_MAX, &len);
			strcpy(params->server_cert_path , szVal);
			printf("conf.server_cert_path=%s\n",params->server_cert_path);
		}
		if (params->server_cert_path[0] == 0) {
			printf("Error: -c/--server_cert_path parameter missing\n");
			err = -1;
		}
	}
	if (params->server_private_key_path[0] == 0) {
		if ( access(conf, 0) >= 0  ) {
			read_config(conf, "server_private_key_path", szVal, PATH_MAX, &len);
			strcpy(params->server_private_key_path , szVal);
			printf("conf.server_private_key_path=%s\n",params->server_private_key_path);
		}
		if (params->server_private_key_path[0] == 0) {
			printf("Error: -k/--server_private_key_path missing\n");
			err = -1;
		}
	}
	return err;
}

int cmd_params_process(int argc, char **argv, struct cmd_params *params)
{
	const static char* _sopts = "hS:E:d:v:s:p:c:k:";
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
	int v;

	if (params == NULL)
		return -1;

	memset(params, 0, sizeof(struct cmd_params));
	params->isv_prod_id = 0xFFFF;
	params->isv_svn = 0xFFFF;
	params->port = 0xFFFF;
	while ((c = getopt_long(argc, argv, _sopts, _lopts, NULL)) != -1) {
		switch (c) {
		case 'h':
			print_help();
			return -1;
		case 'S':
			if (is_str_length_invalid(optarg, MRSIGNER_LEN*2)) {
				printf("Error! MRSigner invalid!\n");
				return -1;
			}
			printf("opt.MRSigner=%s\n", optarg);
			hexstr2buff(optarg, params->MRSigner, MRSIGNER_LEN);
			break;
		case 'E':
			if (is_str_length_invalid(optarg, MRENCLAVE_LEN*2)) {
				printf("Error! MREnclave invalid!\n");
				return -1;
			}
			printf("opt.MREnclave=%s\n", optarg);
			hexstr2buff(optarg, params->MREnclave, MRSIGNER_LEN);
			break;
		case 'd':
			v = atoi(optarg);
			if (v < 0 || v > 0xFFFF) {
				printf("Error! isv_prod_id value is invalid!\n");
				return -1;
			}
			printf("opt.isv_prod_id=%d\n", v);
			params->isv_prod_id = v;
			break;
		case 'v':
			v = atoi(optarg);
			if (v < 0 || v > 0xFFFF) {
				printf("Error! isv_svn value is invalid(empty)!\n");
				return -1;
			}
			printf("opt.isv_svn=%d\n", v);
			params->isv_svn = v;
			break;
		case 's':
			if (is_str_length_invalid(optarg, WRAP_KEY_SIZE*2)) {
				printf("Error! secret value is invalid!\n");
				return -1;
			}
			printf("opt.secret=%s\n", optarg);
			strcpy(params->secret , optarg);
			break;
		case 'p':
			v = atoi(optarg);
			if (v < 0 || v > 0xFFFF) {
				printf("Error! port value is invalid!\n");
				return -1;
			}
			printf("opt.port=%d\n", v);
			params->port = v;
			break;
		case 'c':
			if (optarg) {
				strcpy(params->server_cert_path , optarg);
				printf("opt.server_cert_path=%s\n", optarg);
			}
			break;
		case 'k':
			if (optarg) {
				strcpy(params->server_private_key_path , optarg);
				printf("opt.server_private_key_path=%s\n", optarg);
			}
			break;
		default:
			printf("Error occurred during processing command-line options!\n");
			print_help();
			return -1;
		}
	}
	return load_from_conf_file_if_missing(params);
}

