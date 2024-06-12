#
# Copyright (c) 2024 Intel Corporation
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

ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8

# Add steps here to set up dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends apt-utils \
    && apt-get install -y \
        ca-certificates \
        build-essential \
        autoconf \
        libtool \
        python3-pip \
        python3-dev \
        zlib1g-dev \
        lsb-release \
        wget \
        unzip \
        git \
        vim \
        jq

RUN ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /opt/intel

ENV DCAP_PKG_VERSION=1.19
ENV DCAP_SDK_VERSION=2.22.100.3
RUN wget https://download.01.org/intel-sgx/sgx-dcap/${DCAP_PKG_VERSION}/linux/distro/ubuntu22.04-server/sgx_debian_local_repo.tgz \
    && wget https://download.01.org/intel-sgx/sgx-dcap/${DCAP_PKG_VERSION}/linux/distro/ubuntu22.04-server/sgx_linux_x64_sdk_${DCAP_SDK_VERSION}.bin \
    && echo "deb [trusted=yes arch=amd64] file:/opt/intel/sgx_debian_local_repo $(lsb_release -sc) main" > /etc/apt/sources.list.d/sgx_debian_local_repo.list \
    && tar -zxvf sgx_debian_local_repo.tgz \
    && rm -rf sgx_debian_local_repo.tgz

RUN apt-get update \
    && apt-get install -y \
        tdx-qgs \
        sgx-ra-service \
        libsgx-dcap-ql-dev \
        libsgx-dcap-default-qpl-dev \
        libsgx-enclave-common-dev \
    && apt-get install -y \
        libtdx-attest-dev \
    && apt-get install -y \
        libsgx-dcap-quote-verify-dev \
        libsgx-ae-qve

ENV DCAP_REPO_VERSION=DCAP_${DCAP_PKG_VERSION}
RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git \
    && cd SGXDataCenterAttestationPrimitives \
    && git checkout ${DCAP_REPO_VERSION}

RUN chmod +x /opt/intel/sgx_linux_x64_sdk_${DCAP_SDK_VERSION}.bin \
    && echo "no\n/opt/intel" | /opt/intel/sgx_linux_x64_sdk_${DCAP_SDK_VERSION}.bin \
    && rm /opt/intel/sgx_linux_x64_sdk_${DCAP_SDK_VERSION}.bin
ENV INTEL_SGXSDK_INCLUDE=/opt/intel/sgxsdk/include

# cmake tool chain
ARG CMAKE_VERSION=3.19.6
RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

# GRPC src
ENV GRPC_PATH=/grpc
ENV GRPC_VERSION=v1.38.1
RUN git clone --recurse-submodules -b ${GRPC_VERSION} https://github.com/grpc/grpc ${GRPC_PATH}
RUN sed -i "s/std::max(SIGSTKSZ, 65536)/std::max<size_t>(SIGSTKSZ, 65536)/g" ${GRPC_PATH}/third_party/abseil-cpp/absl/debugging/failure_signal_handler.cc

# cczoo src
ENV CCZOO_PATH=/cczoo
# https://github.com/intel/confidential-computing-zoo/commits/branch0.1/grpc-ra-tls
ENV CCZOO_VERSION=051bbc9f4d6a0c9476341f33161e5775536f62b4
RUN git clone https://github.com/intel/confidential-computing-zoo ${CCZOO_PATH} \
    && cd ${CCZOO_PATH} \
    && git checkout ${CCZOO_VERSION}
RUN cd ${CCZOO_PATH}/cczoo/grpc-ra-tls/grpc \
    && cp -r common/* ${GRPC_PATH} \
    && cp -r v1.38.1/* ${GRPC_PATH}

RUN pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir -r ${GRPC_PATH}/requirements.txt \
    && pip3 install --no-cache-dir cython==0.29.36

# Build tdx_report_parser
RUN cd ${CCZOO_PATH}/utilities/tdx/tdx_report_parser \
    && make \
    && cp tdx_report.out ${INSTALL_PREFIX}/bin/tdx_report_parser

# Build grpc
ENV SGX_RA_TLS_BACKEND=TDX
ENV SGX_RA_TLS_SDK=DEFAULT
ENV BUILD_TYPE=Release

COPY patches ${GRPC_PATH}

RUN cd ${GRPC_PATH} \
    && git apply *.diff

RUN cd ${GRPC_PATH}/examples/cpp/ratls \
    && ./build.sh \
    && cp ${GRPC_PATH}/dynamic_config.tdx.json ./build/dynamic_config.json

COPY configs /

# Workspace
ENV WORK_SPACE_PATH=${GRPC_PATH}/examples/cpp/ratls/build
WORKDIR ${WORK_SPACE_PATH}

RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/bin/bash", "-c", "/entrypoint.sh"]
