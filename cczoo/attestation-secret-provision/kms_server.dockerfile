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

FROM ubuntu:18.04

ARG http_proxy
ARG https_proxy
ARG no_proxy
ENV http_proxy=$http_proxy
ENV https_proxy=$https_proxy
ENV no_proxy=$no_proxy
ENV DEBIAN_FRONTEND=noninteractive

COPY kms_server/ /kms_server/

RUN apt-get update \
    && apt-get install -y curl \
    software-properties-common apt-utils \
    libcap2-bin

# Install Vault as KMS
RUN curl -fsSL https://apt.releases.hashicorp.com/gpg | apt-key add - \
    && apt-add-repository "deb [arch=amd64] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
    && apt-get update \
    && apt-get install -y vault

RUN setcap cap_ipc_lock= /usr/bin/vault

RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*