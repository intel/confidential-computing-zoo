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

# https://github.com/oscarlab/graphene/blob/master/Tools/gsc/images/graphene_aks.latest.dockerfile

ARG base_image=ubuntu:20.04
FROM ${base_image}

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
        unzip \
        wget \
        git \
        vim \
        jq

# Intel SGX PPA
ENV DCAP_PKG_VERSION=1.19
RUN mkdir -p /opt/intel && cd /opt/intel \
    && wget https://download.01.org/intel-sgx/sgx-dcap/${DCAP_PKG_VERSION}/linux/distro/ubuntu20.04-server/sgx_debian_local_repo.tgz \
    && tar -zxvf sgx_debian_local_repo.tgz \
    && rm -rf sgx_debian_local_repo.tgz \
    && echo "deb [trusted=yes arch=amd64] file:/opt/intel/sgx_debian_local_repo $(lsb_release -sc) main" | tee /etc/apt/sources.list.d/sgx_debian_local_repo.list

# RUN echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu $(lsb_release -sc) main" | tee /etc/apt/sources.list.d/intel-sgx.list \
#     && wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add -

# Install SGX-PSW
RUN apt-get update \
    && apt-get install -y libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-quote-ex-dev libsgx-qe3-logic sgx-aesm-service

# Install SGX-DCAP
RUN apt-get update \
    && apt-get install -y libsgx-dcap-ql-dev libsgx-dcap-default-qpl libsgx-dcap-quote-verify-dev libsgx-dcap-default-qpl-dev

# Install CMAKE
ARG CMAKE_VERSION=3.19.6
RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

# Install CMAKE
ARG CMAKE_VERSION=3.19.6
RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

# Install BAZEL
ARG BAZEL_VERSION=3.1.0
RUN wget "https://github.com/bazelbuild/bazel/releases/download/${BAZEL_VERSION}/bazel_${BAZEL_VERSION}-linux-x86_64.deb" \
    && dpkg -i bazel_*.deb \
    && rm bazel_*.deb

# Gramine
ENV GRAMINEDIR=/gramine
ENV GRAMINE_VERSION=v1.6

RUN apt-get update \
    && apt-get install -y bison gawk nasm python3-click python3-pyelftools python3-jinja2 ninja-build pkg-config \
    libcurl4-openssl-dev libprotobuf-c-dev python3-protobuf protobuf-c-compiler \
    libgmp-dev libmpfr-dev libmpc-dev libisl-dev

RUN pip3 install --upgrade pip \
    && pip3 install 'meson>=0.56' 'tomli>=1.1.0' 'tomli-w>=0.4.0' cryptography

RUN git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && cd ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

ENV SGX_DRIVER_INC_PATH=${GRAMINEDIR}/driver_inc
RUN mkdir -p ${SGX_DRIVER_INC_PATH}/asm \
    && wget https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/plain/arch/x86/include/uapi/asm/sgx.h?h=v5.11 -O ${SGX_DRIVER_INC_PATH}/asm/sgx.h

COPY gramine/patches ${GRAMINEDIR}
RUN cd ${GRAMINEDIR} \
    && git apply *.diff

# Build gramine
# https://gramine.readthedocs.io/en/latest/devel/building.html
ENV SGX=1
ENV WERROR=1
ENV BUILD_TYPE=release
RUN cd ${GRAMINEDIR} \
    && LD_LIBRARY_PATH="" meson setup build/ --buildtype=${BUILD_TYPE} -Dprefix=${INSTALL_PREFIX} -Ddirect=enabled -Dsgx=enabled -Ddcap=enabled -Dlibgomp=enabled -Dsgx_driver_include_path=${SGX_DRIVER_INC_PATH} \
    && LD_LIBRARY_PATH="" ninja -C build/ \
    && LD_LIBRARY_PATH="" ninja -C build/ install

# Install mbedtls
RUN cd ${GRAMINEDIR}/build/subprojects/mbedtls-mbedtls* \
    && cp -r *_gramine.a ${INSTALL_PREFIX}/lib \
    && cp -r ${GRAMINEDIR}/build/subprojects/mbedtls-curl/include/* ${INSTALL_PREFIX}/include

# Install cJSON
RUN cd ${GRAMINEDIR}/subprojects/cJSON*/ \
    && make static \
    && cp -r *.a ${INSTALL_PREFIX}/lib \
    && mkdir -p ${INSTALL_PREFIX}/include/cjson \
    && cp -r *.h ${INSTALL_PREFIX}/include/cjson

RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*

ENV RA_TLS_CERT_SIGNATURE_ALGO=RSA
ENV RA_TLS_ALLOW_HW_CONFIG_NEEDED=1
ENV RA_TLS_ALLOW_SW_HARDENING_NEEDED=1
# ENV RA_TLS_ALLOW_OUTDATED_TCB_INSECURE=1
# ENV RA_TLS_ALLOW_DEBUG_ENCLAVE_INSECURE=1

RUN gramine-sgx-gen-private-key

COPY configs /
# COPY patches/libsgx_dcap_quoteverify.so  /usr/lib64/

# Workspace
ENV WORK_SPACE_PATH=${GRAMINEDIR}/CI-Examples
WORKDIR ${WORK_SPACE_PATH}
