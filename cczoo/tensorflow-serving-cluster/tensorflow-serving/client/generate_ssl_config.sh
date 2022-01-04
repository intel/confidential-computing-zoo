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

#!/usr/bin/env bash

set -e

service_domain_name=$1

rm -rf ssl_configure
mkdir ssl_configure
cd ssl_configure

# https://kubernetes.github.io/ingress-nginx/examples/PREREQUISITES/#client-certificate-authentication
openssl req -x509 -sha256 -nodes -days 365 -newkey rsa:2048 -keyout server.key -out server.crt -subj "/CN=${service_domain_name}"

# Generate tls configure
## https://stackoverflow.com/questions/59199419/using-tensorflow-model-server-with-ssl-configuration

echo "server_key: '`cat server.key | paste -d "" -s`'" >> ssl.cfg
echo "server_cert: '`cat server.crt | paste -d "" -s`'" >> ssl.cfg
echo "client_verify: false" >> ssl.cfg

sed -i "s/-----BEGIN PRIVATE KEY-----/-----BEGIN PRIVATE KEY-----\\\n/g" ssl.cfg
sed -i "s/-----END PRIVATE KEY-----/\\\n-----END PRIVATE KEY-----/g" ssl.cfg
sed -i "s/-----BEGIN CERTIFICATE-----/-----BEGIN CERTIFICATE-----\\\n/g" ssl.cfg
sed -i "s/-----END CERTIFICATE-----/\\\n-----END CERTIFICATE-----/g" ssl.cfg

echo "Generate server.key server.crt and ssl.cfg successfully!"
#cat ssl.cfg
cd -

