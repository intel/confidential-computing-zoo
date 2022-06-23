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

ARG BASE_IMAGE=occlum-sgx-dev:latest
FROM ${BASE_IMAGE}

RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v3.19.6/cmake-3.19.6-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

ENV GRPC_ROOT=/grpc
ENV GRPC_PATH=${GRPC_ROOT}/src
ENV SGX_RA_TLS_BACKEND=OCCLUM
ENV BUILD_TYPE=Release

ARG GRPC_V138_VERSION=v1.38.1
ARG GRPC_V138_PATH=${GRPC_ROOT}/${GRPC_V138_VERSION}
RUN git clone --recurse-submodules -b ${GRPC_V138_VERSION} https://github.com/grpc/grpc ${GRPC_V138_PATH}

RUN ln -s ${GRPC_V138_PATH} ${GRPC_PATH}

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1

RUN pip3 install --upgrade pip setuptools==44.1.1 \
    && pip3 install -r ${GRPC_PATH}/requirements.txt

RUN apt-get update \
    && apt-get install -y lsb-release golang strace gdb ctags curl zip sshpass

RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*

COPY grpc/common ${GRPC_V138_PATH}
COPY grpc/v1.38.1 ${GRPC_V138_PATH}
COPY occlum/demos /root/demos
