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

FROM occlum/occlum:0.26.3-ubuntu18.04

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:/usr/lib:/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8
ENV OCCLUM_VERSION=0.26.3
ENV OCCLUM_PATH=/occlum

RUN apt-get update \
    && apt-get install -y --no-install-recommends apt-utils \
    && apt-get install -y ca-certificates build-essential \
        autoconf libtool python3-pip python3-dev git wget \
        unzip zip vim jq lsb-release golang strace gdb ctags \
        curl sshpass software-properties-common

RUN git clone -b ${OCCLUM_VERSION} https://github.com/occlum/occlum ${OCCLUM_PATH}

RUN cd ${OCCLUM_PATH} \
    && make submodule \
    && cd ${OCCLUM_PATH}/demos/remote_attestation/dcap/dcap_lib \
    && cargo build --all-targets \
    && cp target/debug/libdcap_quote.a ${INSTALL_PREFIX}/lib/ \
    && cp ../c_app/dcap_quote.h ${INSTALL_PREFIX}/include/

RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v3.19.6/cmake-3.19.6-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

# Install Vault as KMS
# https://learn.hashicorp.com/tutorials/vault/getting-started-install
RUN wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg >/dev/null \
    && gpg --no-default-keyring --keyring /usr/share/keyrings/hashicorp-archive-keyring.gpg --fingerprint \
    && echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list \
    && apt-get update \
    && apt-get install -y vault \
    && apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*

RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

ENV WORK_SAPCE=/root
ENV CCZOO_ROOT=${WORK_SAPCE}/cczoo
ENV CCZOO_PATH=${CCZOO_ROOT}/src
ENV GRPC_ROOT=${WORK_SAPCE}/grpc
ENV GRPC_PATH=${GRPC_ROOT}/src
ENV SGX_RA_TLS_BACKEND=OCCLUM
ENV SGX_RA_TLS_SDK=DEFAULT
ENV BUILD_TYPE=Release

ARG CCZOO_VERSION=v0.4
ARG CCZOO_VERSION_PATH=${CCZOO_ROOT}/${CCZOO_VERSION}
RUN git clone -b ${CCZOO_VERSION} https://github.com/intel/confidential-computing-zoo.git ${CCZOO_VERSION_PATH}

RUN ln -s ${CCZOO_VERSION_PATH} ${CCZOO_PATH}

ARG GRPC_VERSION=v1.38.1
ARG GRPC_VERSION_PATH=${GRPC_ROOT}/${GRPC_VERSION}
RUN git clone --recurse-submodules -b ${GRPC_VERSION} https://github.com/grpc/grpc.git ${GRPC_VERSION_PATH}

RUN cp -r ${CCZOO_PATH}/cczoo/grpc-ra-tls/grpc/common/* ${GRPC_VERSION_PATH} \
    && cp -r ${CCZOO_PATH}/cczoo/grpc-ra-tls/grpc/${GRPC_VERSION}/* ${GRPC_VERSION_PATH}

RUN ln -s ${GRPC_VERSION_PATH} ${GRPC_PATH}

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1

RUN pip3 install --upgrade pip setuptools==44.1.1 \
    && pip3 install -r ${GRPC_PATH}/requirements.txt

COPY store_secrets ${WORK_SAPCE}/store_secrets
COPY secret_provision ${WORK_SAPCE}/secret_provision
COPY asp_service ${WORK_SAPCE}/asp_service
COPY dcap_configs /
COPY occlum ${WORK_SAPCE}

WORKDIR /root/demos/attestation-secret-provision
