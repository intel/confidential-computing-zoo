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

ARG base_image=clf-client:gramine1.3-ubuntu20.04
FROM ${base_image}


# Parent Image Env
ENV CLF_APP_FOLDER=/clf/cczoo/cross_lang_framework/clf_client
ENV GRAMINE_FOLDER=/gramine

#--------------------------------
# Build and Run Sample App
#--------------------------------
ENV APP_PATH=/app_repo
# download app code, your should replace this with your app.
RUN n=0; until [ $n -ge 100 ] ;  do echo $n; n=$(($n+1)); git clone https://github.com/intel/confidential-computing-zoo.git ${APP_PATH} && break; sleep 1; done
RUN cd ${CLF_APP_FOLDER} \
    && git checkout branch-dev/cross_lang_framework \
    && cp -rf ${APP_PATH}/cczoo/cross_lang_framework/clf_client/app ${CLF_APP_FOLDER}/ \
    && echo "---build sample app---" \
    && cd ${CLF_APP_FOLDER}/app \
    && GRAMINEDIR=${GRAMINE_FOLDER} SGX_SIGNER_KEY=${HOME}/.config/gramine/enclave-key.pem make SGX=1

# Workspace
WORKDIR ${CLF_APP_FOLDER}/app

