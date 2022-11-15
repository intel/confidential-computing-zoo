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

ARG BASE_IMAGE
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
        git \
        zlib1g-dev \
        wget \
        unzip \
        vim \
        jq

ARG BASE_IMAGE=ubuntu:20.04
RUN if [ "${BASE_IMAGE}" = "ubuntu:18.04" ] ; then \
        echo "use ubuntu:18.04 as base image" ; \
        echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu bionic main" | tee /etc/apt/sources.list.d/intel-sgx.list ; \
    elif [ "${BASE_IMAGE}" = "ubuntu:20.04" ] ; then \
        echo "use ubuntu:20.04 as base image" ; \
        echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main" | tee /etc/apt/sources.list.d/intel-sgx.list ; \
    else \
        echo "wrong base image!" ;\
    fi

RUN wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add - \
    && apt-get update

# Install SGX-PSW
RUN apt-get install -y libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-quote-ex-dev libsgx-qe3-logic sgx-aesm-service

# Install SGX-DCAP
RUN apt-get install -y libsgx-dcap-ql-dev libsgx-dcap-default-qpl libsgx-dcap-quote-verify-dev libsgx-dcap-default-qpl-dev

# Gramine
ENV GRAMINEDIR=/gramine
ENV SGX_DCAP_VERSION=DCAP_1.11
ENV GRAMINE_VERSION=v1.2
ENV ISGX_DRIVER_PATH=${GRAMINEDIR}/driver
ENV WERROR=1
ENV SGX=1

RUN apt-get install -y bison gawk nasm python3-click python3-jinja2 ninja-build pkg-config \
    libcurl4-openssl-dev libprotobuf-c-dev python3-protobuf protobuf-c-compiler \
    libgmp-dev libmpfr-dev libmpc-dev libisl-dev

RUN pip3 install --upgrade pip \
    && pip3 install toml meson cryptography

RUN git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && cd ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && cd ${ISGX_DRIVER_PATH} \
    && git checkout ${SGX_DCAP_VERSION}

RUN cd ${GRAMINEDIR} \
    && LD_LIBRARY_PATH="" meson setup build/ --buildtype=debug -Dprefix=${INSTALL_PREFIX} -Ddirect=enabled -Dsgx=enabled -Ddcap=enabled -Dsgx_driver=dcap1.10 -Dsgx_driver_include_path=${ISGX_DRIVER_PATH}/driver/linux/include \
    && LD_LIBRARY_PATH="" ninja -C build/ \
    && LD_LIBRARY_PATH="" ninja -C build/ install

# Install mbedtls
RUN cd ${GRAMINEDIR}/build/subprojects/mbedtls-mbedtls* \
    && cp -r *_gramine.a ${INSTALL_PREFIX}/lib \
    && cd ${GRAMINEDIR}/subprojects/mbedtls-mbedtls*/mbedtls-mbedtls* \
    && cp -r include/mbedtls ${INSTALL_PREFIX}/include

# Install cJSON
RUN cd ${GRAMINEDIR}/subprojects/cJSON* \
    && make static \
    && cp -r *.a ${INSTALL_PREFIX}/lib \
    && mkdir -p ${INSTALL_PREFIX}/include/cjson \
    && cp -r *.h ${INSTALL_PREFIX}/include/cjson

RUN gramine-sgx-gen-private-key

COPY configs /

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

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1

RUN pip3 install --upgrade pip \
    && pip3 install -r ${GRPC_PATH}/requirements.txt \
    && pip3 install --upgrade protobuf

RUN apt-get update \
    && apt-get install -y lsb-release golang strace gdb ctags curl zip sshpass

RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*

COPY grpc/common ${GRPC_V138_PATH}
COPY grpc/v1.38.1 ${GRPC_V138_PATH}
COPY gramine/CI-Examples ${GRAMINEDIR}/CI-Examples

RUN if [ "${BASE_IMAGE}" = "ubuntu:18.04" ]; then \
    cd ${GRAMINEDIR}/CI-Examples/psi/python/ && \
    sed -i "41s/# //" python.manifest.template && \
    sed -i "42s/^/#/" python.manifest.template && \
    sed -i "64s/# //" python.manifest.template && \
    sed -i "65s/^/#/" python.manifest.template; \
    fi

RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*
