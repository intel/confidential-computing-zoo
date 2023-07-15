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

# https://github.com/oscarlab/graphene/blob/master/Tools/gsc/images/graphene_aks.latest.dockerfile

FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8

# Install initial dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget \
        ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /dcap
RUN wget -q https://download.01.org/intel-sgx/sgx-dcap/1.19/linux/distro/ubuntu20.04-server/sgx_debian_local_repo.tgz \
    && tar -xvf sgx_debian_local_repo.tgz
RUN ["/bin/bash", "-c", "set -o pipefail && echo 'deb [trusted=yes arch=amd64] file:/dcap/sgx_debian_local_repo focal main' | tee /etc/apt/sources.list.d/intel-sgx.list"]

RUN apt-get update && apt-get install -y --no-install-recommends \
        apt-utils \
        build-essential \
        autoconf \
        libtool \
        python3-pip \
        python3-dev \
        git \
        zlib1g-dev \
        unzip \
        vim \
        jq \
        gawk bison python3-click python3-jinja2 golang ninja-build \
        libprotobuf-c-dev python3-protobuf protobuf-c-compiler protobuf-compiler\
        libgmp-dev libmpfr-dev libmpc-dev libisl-dev nasm \
# Install SGX PSW
        libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-quote-ex-dev libsgx-qe3-logic sgx-aesm-service \
# Install SGX DCAP
        libsgx-dcap-ql-dev libsgx-dcap-quote-verify-dev \
# Install dependencies for Azure DCAP Client
        libssl-dev libcurl4-openssl-dev pkg-config nlohmann-json3-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Build and install the Azure DCAP Client (Release 1.12.1)
WORKDIR /azure
ARG AZUREDIR=/azure
RUN git clone https://github.com/microsoft/Azure-DCAP-Client ${AZUREDIR} \
    && git checkout bc7b484e5fa9a8daa684032c7270f76800b7007d \
    && git submodule update --recursive --init

WORKDIR /azure/src/Linux
RUN ./configure \
    && make DEBUG=1 \
    && make install \
    && cp libdcap_quoteprov.so /usr/lib/x86_64-linux-gnu/

# Gramine
ENV GRAMINEDIR=/gramine
ENV SGX_DCAP_VERSION=DCAP_1.11
ENV GRAMINE_VERSION=v1.2
ENV ISGX_DRIVER_PATH=${GRAMINEDIR}/driver
ENV WERROR=1
ENV SGX=1

RUN pip3 install --no-cache-dir 'toml==0.10.2' 'meson==1.2.2' 'cryptography==41.0.4'

WORKDIR ${GRAMINEDIR}
RUN git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

WORKDIR ${ISGX_DRIVER_PATH}
RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && git checkout ${SGX_DCAP_VERSION}

ARG BUILD_TYPE=release
WORKDIR ${GRAMINEDIR}
RUN LD_LIBRARY_PATH="" meson setup build/ --buildtype=${BUILD_TYPE} -Dprefix=${INSTALL_PREFIX} -Ddirect=enabled -Dsgx=enabled -Ddcap=enabled -Dsgx_driver=dcap1.10 -Dsgx_driver_include_path=${ISGX_DRIVER_PATH}/driver/linux/include \
    && LD_LIBRARY_PATH="" ninja -C build/ \
    && LD_LIBRARY_PATH="" ninja -C build/ install

# Install mbedtls
RUN cd ${GRAMINEDIR}/build/subprojects/mbedtls-mbedtls* \
    && cp -r -- *_gramine.a ${INSTALL_PREFIX}/lib \
    && cd ${GRAMINEDIR}/subprojects/mbedtls-mbedtls*/mbedtls-mbedtls* \
    && cp -r include/mbedtls ${INSTALL_PREFIX}/include

# Install cJSON
RUN cd ${GRAMINEDIR}/subprojects/cJSON*/ \
    && make static \
    && cp -r -- *.a ${INSTALL_PREFIX}/lib \
    && mkdir -p ${INSTALL_PREFIX}/include/cjson \
    && cp -r -- *.h ${INSTALL_PREFIX}/include/cjson

RUN echo "enabled=0" > /etc/default/apport \
    && echo "exit 0" > /usr/sbin/policy-rc.d

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*

RUN gramine-sgx-gen-private-key

COPY configs /

# Workspace
ENV WORK_SPACE_PATH=${GRAMINEDIR}
WORKDIR ${WORK_SPACE_PATH}
