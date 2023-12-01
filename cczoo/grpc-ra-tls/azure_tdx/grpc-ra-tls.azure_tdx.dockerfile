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
        ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /dcap
RUN wget https://download.01.org/intel-sgx/sgx-dcap/1.19/linux/distro/ubuntu20.04-server/sgx_debian_local_repo.tgz \
    && tar -xvf sgx_debian_local_repo.tgz
RUN ["/bin/bash", "-c", "set -o pipefail && echo 'deb [trusted=yes arch=amd64] file:/dcap/sgx_debian_local_repo focal main' | tee /etc/apt/sources.list.d/intel-sgx.list"]

RUN apt-get update && apt-get install -y --no-install-recommends \
        apt-utils \
        python3-pip \
        git \
        vim \
# required for gRPC build
        build-essential cmake libcurl4-openssl-dev nlohmann-json3-dev \
# SGX PSW packages required for gRPC build
        libtdx-attest libtdx-attest-dev \
# required for bazel setup
        unzip \
# required for attestation client
        libjsoncpp-dev libboost-all-dev libssl1.1 tpm2-tools \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Azure confidential-computing-cvm-guest-attestation
WORKDIR /
RUN git clone -b tdx-preview https://github.com/Azure/confidential-computing-cvm-guest-attestation
WORKDIR /confidential-computing-cvm-guest-attestation
RUN git checkout e045e8f52543f823f9a85d1b33338f99dec70397
WORKDIR /confidential-computing-cvm-guest-attestation/tdx-attestation-app
RUN dpkg -i package/azguestattestation1_1.0.3_amd64.deb

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

COPY grpc/common ${GRPC_VERSION_PATH}
COPY grpc/${GRPC_VERSION} ${GRPC_VERSION_PATH}
COPY grpc/common/attest_config.json /etc

# Install Python dependencies
RUN pip3 install --upgrade --no-cache-dir \
        'pip==23.1.*' 'certifi==2022.12.7' 'requests==2.31.*' 'urllib3==1.26.*' 'cython==0.29.36'\
    && pip3 install --no-cache-dir -r "${GRPC_PATH}/requirements.txt"

# Build grpc ra-tls example server/client
WORKDIR ${GRPC_PATH}/examples/cpp/ratls
RUN build.sh
WORKDIR ${GRPC_PATH}/examples/python/ratls
RUN build.sh

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/pip/* \
    && rm -rf /tmp/*

WORKDIR ${GRPC_PATH}/examples/cpp/ratls/build
