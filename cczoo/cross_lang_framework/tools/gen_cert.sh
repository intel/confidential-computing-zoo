#!/bin/bash

#
# Copyright (c) 2021 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

CA_KEY=ca_private_key.pem
CA_CERT=ca_cert.crt
CHILD_KEY=server_private_key.pem
CHILD_CERT=server_signed_cert.crt

REQ_FILE=__my_cert_req.csr
EXT_FILE=__v3.ext
SRL_FILE=`echo ${CA_CERT} | awk -F '.' '{print $1}'`.srl

# color
COLORLESS="\033[0m"
RED="\033[31m"
GREEN="\033[32m"
YELLOW="\033[33m"

gen_root_cert() {
    echo -e "\n========================================="
    echo -e "Generate Self-signed Root Certification:"
    echo -e "========================================="
    openssl req -newkey rsa:2048 \
            -x509 \
            -sha256 \
            -days 3650 \
            -nodes \
            -out ${CA_CERT} \
            -keyout ${CA_KEY}
}

gen_sign_req() {
    echo -e "\n[Generate sign req]: ..."
    openssl req -new -nodes \
               -newkey rsa:2048 \
               -keyout ${CHILD_KEY} \
               -out ${REQ_FILE}
    echo -e "${GREEN}done${COLORLESS}"
}

create_v3_ext() {
    echo -e "\n[Creating ${EXT_FILE}]: ... \c"
    echo -e "\
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,nonRepudiation,keyEncipherment,dataEncipherment" >${EXT_FILE}
    echo -e "${GREEN}... done${COLORLESS}"
}

sign_child_cert() {
    echo -e "\n[Sign child certification]: ..."
    openssl x509 -req \
               -in ${REQ_FILE} \
               -days 365 \
               -extfile ${EXT_FILE} \
               -CA ${CA_CERT}  \
               -CAkey ${CA_KEY}  \
               -CAcreateserial \
               -out ${CHILD_CERT}
    echo -e "${GREEN}... done${COLORLESS}"
}

display_result() {
    echo -e "\n* root private key:"
    echo -e "$(find `pwd` -name ${CA_KEY})"
    echo -e "* root certification:"
    echo -e "$(find `pwd` -name ${CA_CERT})"

    echo -e "* child private key:"
    echo -e "$(find `pwd` -name ${CHILD_KEY})"
    echo -e "* child certification:"
    echo -e "$(find `pwd` -name ${CHILD_CERT})"
}

do_clean() {
    rm ${REQ_FILE}
    rm ${EXT_FILE}
    rm ${SRL_FILE}
}

generate_child_cert() {
    echo -e "\n========================================="
    echo -e "Generate Child Certification"
    echo -e "========================================="

    create_v3_ext

    gen_sign_req

    sign_child_cert

    display_result

    do_clean
}

helper() {
    echo -e "./gen_cert.sh [-r] [-c]"
    echo -e "-r\tGenerate root certification (e.g. ca_cert.crt), used in clf_client." | sed "s/./&\n\t/72;P;D"
    echo -e "-c\tGenerate child certification and private key, used in clf_server." | sed "s/./&\n\t/72;P;D"
    echo -e "\tRoot certification is used to sign the child certification, so root certification should be generated first.\
 The generated files should be put into folder clf_server/certs/, replace existing files:\
 (e.g. server_private_key.pem and server_signed_cert.crt)" | sed "s/./&\n\t/72;P;D"
}

if [ $# -eq 0 ];
then
    helper
fi

while getopts "hrc" OPT &> /dev/null ; do
    case "$OPT" in
        h)
            helper
            exit 0 ;;
        r)
            gen_root_cert ;;
        c)
            generate_child_cert ;;
        *)
            echo -e "Invalid Parameters."
            helper
            exit 1 ;;
    esac
done
