#!/bin/bash

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

export VAULT_ADDR='http://127.0.0.1:8200'
vault operator init -key-shares=1 -key-threshold=1 > init_status
export UNSEAL_KEY=`cat init_status | grep "Unseal Key" | awk '{print $4}'`
export ROOT_TOKEN=`cat init_status | grep "Root Token" | awk '{print $4}'`
export VAULT_TOKEN=$ROOT_TOKEN
vault operator unseal $UNSEAL_KEY
echo "ROOT_TOKEN: "
echo $ROOT_TOKEN
echo "UNSEAL KEY: "
echo $UNSEAL_KEY

# Secrets for APP1
vault secrets enable -path=occlum/1 kv
occlum gen-image-key image_key
vault kv put occlum/1/image_key key=`cat image_key`
openssl genrsa -out private_key 1024
openssl rsa -in private_key -pubout -out public_key
vault kv put occlum/1/rsa_pubkey key=@public_key
vault kv put occlum/1/rsa_prikey key=@private_key
# Secrets for APP2
vault secrets enable -path=occlum/2 kv
occlum gen-image-key image_key
vault kv put occlum/2/image_key key=`cat image_key`
openssl genrsa -out private_key 1024
openssl rsa -in private_key -pubout -out public_key
vault kv put occlum/2/rsa_pubkey key=@public_key
vault kv put occlum/2/rsa_prikey key=@private_key

rm init_status
rm image_key
rm private_key
rm public_key

# Generate APP token and attach policy
vault policy write app1_policy app1_policy.hcl
APP1_TOKEN=$(vault token create -policy="app1_policy" -field=token)
echo "APP1_TOKEN: "
echo $APP1_TOKEN

vault policy write app2_policy app2_policy.hcl
APP2_TOKEN=$(vault token create -policy="app2_policy" -field=token)
echo "APP2_TOKEN: "
echo $APP2_TOKEN