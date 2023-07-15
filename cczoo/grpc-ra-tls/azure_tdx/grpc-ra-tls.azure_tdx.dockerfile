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

FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8

# Install initial dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget \
        gnupg \
        ca-certificates \
        software-properties-common \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN ["/bin/bash", "-c", "set -o pipefail && echo 'deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main' | tee /etc/apt/sources.list.d/intel-sgx.list"]
RUN ["/bin/bash", "-c", "set -o pipefail && wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add -"]

RUN apt-get update && apt-get install -y --no-install-recommends \
        apt-utils \
        build-essential \
        python3-pip \
        git \
        cmake \
        unzip \
        vim \
# Install SGX PSW
        libsgx-ae-qve libtdx-attest libtdx-attest-dev tdx-qgs libsgx-urts \
# Install SGX DCAP
        libsgx-dcap-quote-verify libsgx-dcap-quote-verify-dev \
# Install dependencies for Azure DCAP Client
        libssl-dev libcurl4-openssl-dev pkg-config nlohmann-json3-dev \
# Install dependencies for Azure confidential-computing-cvm-guest-attestation
        libjsoncpp-dev libboost-all-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Build and install the Azure DCAP Client (Release 1.12.0)
WORKDIR /azure
ARG AZUREDIR=/azure
RUN git clone https://github.com/microsoft/Azure-DCAP-Client ${AZUREDIR} \
    && git checkout 1.12.0 \
    && git submodule update --recursive --init

WORKDIR /azure/src/Linux
RUN ./configure \
    && make DEBUG=1 \
    && make install \
    && cp libdcap_quoteprov.so /usr/lib/x86_64-linux-gnu/

ENV AZDCAP_DEBUG_LOG_LEVEL=ERROR

# bazel
RUN wget -q https://github.com/bazelbuild/bazel/releases/download/3.7.2/bazel-3.7.2-installer-linux-x86_64.sh
RUN bash bazel-3.7.2-installer-linux-x86_64.sh && echo "source /usr/local/lib/bazel/bin/bazel-complete.bash" >> ~/.bashrc

# grpc
ENV GRPC_ROOT=/grpc
ENV GRPC_PATH=${GRPC_ROOT}/src
ENV SGX_RA_TLS_BACKEND=AZURE_TDX
ENV SGX_RA_TLS_SDK=DEFAULT
ENV BUILD_TYPE=Release

ARG GRPC_VERSION=v1.38.1
ARG GRPC_VERSION_PATH=${GRPC_ROOT}/${GRPC_VERSION}
RUN git clone --recurse-submodules -b ${GRPC_VERSION} https://github.com/grpc/grpc ${GRPC_VERSION_PATH}

RUN ln -s ${GRPC_VERSION_PATH} ${GRPC_PATH}

# Azure confidential-computing-cvm-guest-attestation
WORKDIR /
RUN git clone -b tdx-preview https://github.com/Azure/confidential-computing-cvm-guest-attestation
WORKDIR /confidential-computing-cvm-guest-attestation/tdx-attestation-app
RUN wget -q http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_amd64.deb \
    && dpkg -i libssl1.1_1.1.1f-1ubuntu2_amd64.deb \
    && rm libssl1.1_1.1.1f-1ubuntu2_amd64.deb
RUN dpkg -i package/azguestattestation1_1.0.3_amd64.deb 

# patch grpc
COPY grpc/common ${GRPC_VERSION_PATH}
COPY grpc/${GRPC_VERSION} ${GRPC_VERSION_PATH}

COPY grpc/common/azure_tdx_config.json /etc

# build grpc and ra-tls example server/client
WORKDIR ${GRPC_PATH}/examples/cpp/ratls
RUN build.sh

# install python dependencies
RUN pip3 install --upgrade --no-cache-dir 'pip==23.1.*' 'certifi==2022.12.7' 'requests==2.31.*' 'urllib3==1.26.*' \
    && pip3 install --no-cache-dir -r ${GRPC_PATH}/requirements.txt

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/pip/* \
    && rm -rf /tmp/*

WORKDIR ${GRPC_PATH}/examples/cpp/ratls/build
