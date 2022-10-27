#
# Copyright (c) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#!/bin/bash
set -e
COLORLESS="\033[0m"
RED="\033[31m"
GREEN="\033[32m"
YELLOW="\033[33m"

#below is fake secret, you need to replace with your valid ones
echo -e "ccp-cli pack ${GREEN}--app-entry${COLORLESS}=\"/usr/bin/java\"" 
echo -e "             ${GREEN}--memsize${COLORLESS}=8192M ${GREEN}--thread${COLORLESS}=64" 
echo -e "             ${GREEN}--tmpl${COLORLESS}=clf_client"
echo -e "             ${GREEN}--secret-id${COLORLESS}=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
echo -e "             ${GREEN}--secret-key${COLORLESS}=kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk"
echo -e "             ${GREEN}--capp-id${COLORLESS}=capp-ODdjZWZhOWYt"
echo -e "             ${GREEN}--app-image${COLORLESS}=clf-client:gramine1.3-ubuntu20.04"
echo -e "             ${GREEN}--app-type${COLORLESS}=image"
echo -e "             ${GREEN}--start${COLORLESS}=/clf/cczoo/cross_lang_framework/clf_client/app"
echo -e ""
# just an example about how to run
echo -e "docker run -ti ${GREEN}--device${COLORLESS} /dev/sgx_enclave ${GREEN}--device${COLORLESS} /dev/sgx_provision"
echo -e "             ${GREEN}--add-host${COLORLESS}=VM-30-8-ubuntu:10.0.30.8 clf-client:gramine1.3-ubuntu20.04"
echo -e "             -Xmx4G clf_test VM-30-8-ubuntu"
echo -e ""

