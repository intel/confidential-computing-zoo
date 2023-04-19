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

ARG BASE_IMAGE=gramine-sgx-dev:v1.2-anolisos
FROM ${BASE_IMAGE}

RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v3.19.6/cmake-3.19.6-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

ENV GRPC_ROOT=/grpc
ENV GRPC_PATH=${GRPC_ROOT}/src
ENV SGX_RA_TLS_BACKEND=GRAMINE

ARG GRPC_V138_VERSION=v1.38.1
ARG GRPC_V138_PATH=${GRPC_ROOT}/${GRPC_V138_VERSION}
RUN git clone --recurse-submodules -b ${GRPC_V138_VERSION} https://github.com/grpc/grpc ${GRPC_V138_PATH}

RUN ln -s ${GRPC_V138_PATH} ${GRPC_PATH}

RUN update-alternatives --install /usr/bin/unversioned-python python /usr/bin/python3 1

RUN pip3 install --upgrade pip \
    && pip3 install -r ${GRPC_PATH}/requirements.txt

RUN yum -y update \
    && yum -y install redhat-lsb golang strace gdb ctags curl zip sshpass jq

RUN yum -y clean all && rm -rf /var/cache

COPY grpc/common ${GRPC_V138_PATH}
COPY grpc/v1.38.1 ${GRPC_V138_PATH}
COPY gramine/CI-Examples ${GRAMINEDIR}/CI-Examples
RUN cd ${GRAMINEDIR}/CI-Examples/psi/python && git apply *.diff \
&& cd ${GRAMINEDIR}/CI-Examples/psi/cpp && git apply *.diff

RUN python3 -m pip install --upgrade pip \
    && pip3 uninstall -y six \
    && python3 -m pip install six
