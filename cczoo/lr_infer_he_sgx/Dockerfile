#
# Copyright (c) 2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
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

# Optional build argument to select a build for Azure
ARG AZURE

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8

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

RUN echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main" | tee /etc/apt/sources.list.d/intel-sgx.list ;
RUN wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add - \
    && apt-get update

# Install SGX-PSW
RUN apt-get install -y libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-quote-ex-dev libsgx-qe3-logic sgx-aesm-service

# Install SGX DCAP
RUN apt-get install -y libsgx-dcap-ql-dev libsgx-dcap-quote-verify-dev

# Install SGX-DCAP quote provider library
RUN if [ -z "$AZURE" ]; then \
        # Not a build for Azure, so install the default quote provider library \
        apt-get install -y libsgx-dcap-default-qpl; \
    else \
        # Build for Azure, so install the Azure DCAP Client (Release 1.10.0) \
        AZUREDIR=/azure \
        && apt-get install -y libssl-dev libcurl4-openssl-dev pkg-config software-properties-common \
        && add-apt-repository ppa:team-xbmc/ppa -y \
        && apt-get update \
        && apt-get install -y nlohmann-json3-dev \
        && git clone https://github.com/microsoft/Azure-DCAP-Client ${AZUREDIR} \
        && cd ${AZUREDIR} \
        && git checkout 1.10.0 \
        && git submodule update --recursive --init \
        && cd src/Linux \
        && ./configure \
        && make DEBUG=1 \
        && make install \
        && cp libdcap_quoteprov.so /usr/lib/x86_64-linux-gnu/; \
    fi

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

RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*

RUN gramine-sgx-gen-private-key

RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v3.19.6/cmake-3.19.6-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

ENV WORKSPACE=/lr_infer_he_sgx
WORKDIR ${WORKSPACE}

COPY src ./src
COPY datasets ./datasets
COPY cmake ./cmake
COPY CMakeLists.txt \
     start_service.sh \
     infer_server.manifest.template \
     Makefile ./

RUN cmake -S. -Bbuild \
    && cmake --build build \
    && cp build/src/infer_server . \
    && cp datasets/lrtest_mid_lrmodel.csv . \
    && make clean \
    && ENTRYPOINT=infer_server make

RUN echo "/lr_infer_he_sgx/start_service.sh" >> ~/.bashrc

ENV http_proxy=
ENV https_proxy=
