#
# Copyright (c) 2021 Intel Corporation
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


FROM ubuntu:20.04

ENV GRAMINEDIR=/gramine
ENV ISGX_DRIVER_PATH=${GRAMINEDIR}/driver
ENV WORK_BASE_PATH=${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov
ENV WERROR=1
ENV SGX=1
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Disable debconf warning
RUN ["/bin/bash", "-c", "set -o pipefail && echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections"]

# Install initial dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget \
        gnupg \
        ca-certificates \
        software-properties-common \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN ["/bin/bash", "-c", "set -o pipefail && echo 'deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main' | tee /etc/apt/sources.list.d/intel-sgx.list"]
RUN ["/bin/bash", "-c", "set -o pipefail && wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add -"]
RUN add-apt-repository ppa:team-xbmc/ppa -y

RUN apt-get update && apt-get install -y --no-install-recommends \
        autoconf \
        bison \
        build-essential \
        coreutils \
        gawk \
        git \
        libprotobuf-c-dev \
        protobuf-c-compiler \
        python3-protobuf \
        python3-pip \
        python3-dev \
        libnss-mdns \
        libnss-myhostname \
        lsb-release \
        curl \
        init \
        nasm \
        apt-utils \
        gawk bison python3-click python3-jinja2 golang ninja-build python3 \
        libcurl4-openssl-dev libprotobuf-c-dev python3-protobuf protobuf-c-compiler protobuf-compiler \
# Install SGX PSW
        libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-qe3-logic sgx-aesm-service \
# Install SGX DCAP
        libsgx-dcap-ql-dev libsgx-dcap-quote-verify-dev \
# Install dependencies for Azure DCAP Client
        libssl-dev libcurl4-openssl-dev pkg-config nlohmann-json3-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Build and install the Azure DCAP Client (Release 1.10.0)
WORKDIR /azure
ARG AZUREDIR=/azure
RUN git clone https://github.com/microsoft/Azure-DCAP-Client ${AZUREDIR} \
    && git checkout 1.10.0 \
    && git submodule update --recursive --init

WORKDIR /azure/src/Linux
RUN ./configure \
    && make DEBUG=1 \
    && make install \
    && cp libdcap_quoteprov.so /usr/lib/x86_64-linux-gnu/

# Clone Gramine and Init submodules
# dimakuv/ra-tls-maa
ARG GRAMINE_VERSION=a2166216fd795adfa7391be7fb6398116c317ee3
WORKDIR ${GRAMINEDIR}
RUN git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

# Create SGX driver for header files
WORKDIR ${ISGX_DRIVER_PATH}
RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && git checkout DCAP_1.11

RUN python3 -B -m pip install --no-cache-dir 'wheel>=0.38.0' 'toml>=0.10' 'meson>=0.55' 'cryptography>=41.0.1' 'pyelftools>=0.29'

# Build Gramine
WORKDIR ${GRAMINEDIR}
RUN pwd && meson setup build/ --buildtype=release -Dsgx=enabled -Ddcap=enabled -Dsgx_driver="dcap1.10" -Dsgx_driver_include_path="/gramine/driver/driver/linux/include" \
    && ninja -C build/ \
    && ninja -C build/ install
RUN gramine-sgx-gen-private-key

# Build Secret Provision
ENV RA_TYPE=maa
COPY patches/secret_prov_pf ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov/secret_prov_pf
WORKDIR ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov
RUN make app ${RA_TYPE} RA_TYPE=${RA_TYPE}

COPY patches/ssl ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov/ssl
COPY sgx_default_qcnl.conf /etc/
COPY entrypoint_secret_prov_server.sh /usr/bin/
RUN chmod +x /usr/bin/entrypoint_secret_prov_server.sh
ENTRYPOINT ["/usr/bin/entrypoint_secret_prov_server.sh"]

RUN apt-get clean && rm -rf /var/lib/apt/lists/*
