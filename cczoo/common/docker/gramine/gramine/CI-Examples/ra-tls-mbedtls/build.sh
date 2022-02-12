#
# Copyright (c) 2022 Intel Corporation
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

set -ex

export MBEDTLS_PATH=${GRAMINEDIR}/CI-Examples/ra-tls-mbedtls

cd ${MBEDTLS_PATH}

make clean
make app dcap

cp -r mbedtls/include ${INSTALL_PREFIX}

whereis libmbedtls_gramine libmbedcrypto_gramine libmbedx509_gramine 
whereis libsgx_util libsgx_dcap_quoteverify libdcap_quoteprov.so.*
whereis libra_tls_attest libra_tls_verify_dcap libra_tls_verify_epid

cd -
