#!/usr/bin/bash
#
# Copyright (c) 2023 Intel Corporation
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

if [ $# -ne 2 ]; then
    echo "Usage: $0 resource_group storage_acct_name"
    exit 1
fi

RESOURCE_GROUP=$1
STORAGE_ACCT_NAME=$2
NUM_REPLICAS=4

STORAGE_KEY=$(az storage account keys list --resource-group ${RESOURCE_GROUP} --account-name ${STORAGE_ACCT_NAME} --query "[0].value" -o tsv)

kubectl create namespace gramine-tf-serving

kubectl create secret generic azure-secret --from-literal=azurestorageaccountname=${STORAGE_ACCT_NAME} --from-literal=azurestorageaccountkey=$STORAGE_KEY --namespace=gramine-tf-serving

kubectl apply -f deploy_for_aks.yaml

kubectl scale -n gramine-tf-serving deployment.apps/gramine-tf-serving-deployment --replicas ${NUM_REPLICAS}
