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

CA_KEY=ca_private_key.key
CA_CERT=ca_cert.crt
CHILD_KEY=child_private_key.key
CHILD_CERT=child_cert.crt

gen_root_cert() {
    echo -e "========================================="
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
    echo -e "Generate sign req:"
    openssl req -new -nodes \
               -newkey rsa:2048 \
               -keyout ${CHILD_KEY} \
               -out my_cert_req.csr
}

create_v3_ext() {
    echo -e "Creating v3.ext:"
    echo -e "\
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,nonRepudiation,keyEncipherment,dataEncipherment" >v3.ext
}

sign_child_cert() {
    echo -e "Sign child certification:"
    openssl x509 -req \
               -in my_cert_req.csr \
               -days 365 \
               -extfile v3.ext \
               -CA ${CA_CERT}  \
               -CAkey ${CA_KEY}  \
               -CAcreateserial \
               -out ${CHILD_CERT}
}

display_result() {
    echo -e "* root private key:"
    echo -e "$(find `pwd` -name ${CA_KEY})"
    echo -e "* root certification:"
    echo -e "$(find `pwd` -name ${CA_CERT})"

    echo -e "* child private key:"
    echo -e "$(find `pwd` -name ${CHILD_KEY})"
    echo -e "* child certification:"
    echo -e "$(find `pwd` -name ${CHILD_CERT})"
}

generate_child_cert() {
    echo -e "========================================="
    echo -e "Generate Child Certification"
    echo -e "========================================="

    create_v3_ext

    gen_sign_req

    sign_child_cert

    display_result
}

gen_root_cert
generate_child_cert
