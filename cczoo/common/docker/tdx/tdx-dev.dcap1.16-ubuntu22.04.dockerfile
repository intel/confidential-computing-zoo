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

ENV DCAP_PKG_VERSION=1.16
ENV DCAP_SDK_VERSION=2.19.100.3
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

COPY configs /

RUN chmod +x /opt/intel/sgx_linux_x64_sdk_${DCAP_SDK_VERSION}.bin \
    && echo "no\n/opt/intel" | /opt/intel/sgx_linux_x64_sdk_${DCAP_SDK_VERSION}.bin \
    && rm /opt/intel/sgx_linux_x64_sdk_${DCAP_SDK_VERSION}.bin
ENV INTEL_SGXSDK_INCLUDE=/opt/intel/sgxsdk/include

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1 \
    && update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# only for tdx vsock
# RUN echo 'port=4050' | tee /etc/tdx-attest.conf

# ENTRYPOINT ["/bin/bash", "-c", "sleep infinity"]
