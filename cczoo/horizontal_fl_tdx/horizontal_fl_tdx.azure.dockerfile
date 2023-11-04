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
        python3-pip python3-dev \
        git vim autoconf libtool zlib1g-dev jq \
        gawk bison python3-click python3-jinja2 golang ninja-build \
        libprotobuf-c-dev python3-protobuf protobuf-c-compiler protobuf-compiler\
        libgmp-dev libmpfr-dev libmpc-dev libisl-dev nasm \
        expect cryptsetup e2fsprogs \
# required for gRPC build
        build-essential cmake libcurl4-openssl-dev nlohmann-json3-dev \
# SGX PSW packages required for gRPC build
        libtdx-attest libtdx-attest-dev \
# required for bazel setup
        unzip \
# required for Azure confidential-computing-cvm-guest-attestation
        libjsoncpp-dev libboost-all-dev libssl1.1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Azure confidential-computing-cvm-guest-attestation
WORKDIR /
RUN git clone -b tdx-preview https://github.com/Azure/confidential-computing-cvm-guest-attestation
WORKDIR /confidential-computing-cvm-guest-attestation
RUN git checkout e045e8f52543f823f9a85d1b33338f99dec70397
WORKDIR /confidential-computing-cvm-guest-attestation/tdx-attestation-app
RUN dpkg -i package/azguestattestation1_1.0.3_amd64.deb

# Install Python dependencies
RUN ln -s /usr/bin/python3 /usr/bin/python \
    && pip3 install --no-cache-dir --upgrade \
        'pip>=23.1.2' 'wheel>=0.38.0' 'toml>=0.10.2' 'meson>=1.1.1' 'setuptools==59.6.0' \
        'numpy==1.19.5' 'keras_preprocessing>=1.1.2' 'pandas==1.1.5' 'scikit-learn>=0.0.post5' 'matplotlib==3.3.4' \
        'protobuf==3.19.6'

# bazel
RUN wget -q https://github.com/bazelbuild/bazel/releases/download/3.7.2/bazel-3.7.2-installer-linux-x86_64.sh
RUN bash bazel-3.7.2-installer-linux-x86_64.sh && echo "source /usr/local/lib/bazel/bin/bazel-complete.bash" >> ~/.bashrc

ARG MBEDTLS_VERSION=2.26.0
RUN wget -q https://github.com/Mbed-TLS/mbedtls/archive/refs/tags/v${MBEDTLS_VERSION}.tar.gz \
    && tar -zxvf v${MBEDTLS_VERSION}.tar.gz \
    && cp -r mbedtls-${MBEDTLS_VERSION}/include/mbedtls ${INSTALL_PREFIX}/include

# Config and download TensorFlow
ENV TF_VERSION=v2.6.0
ENV TF_BUILD_PATH=/tf/src
ENV TF_BUILD_OUTPUT=/tf/output
RUN git clone  --recurse-submodules -b ${TF_VERSION} https://github.com/tensorflow/tensorflow ${TF_BUILD_PATH}

# Setup grpc patch
# RA-TLS backend is selected in bazel/ratls.bzl
COPY azure/grpc_ratls.azure.patch ${TF_BUILD_PATH}/third_party/grpc/grpc_ratls.patch

# Apply TensorFlow patch
COPY azure/tf_v2.6.azure.diff ${TF_BUILD_PATH}/tf_v2.6.diff
WORKDIR ${TF_BUILD_PATH}
RUN git apply tf_v2.6.diff

# Build and install TensorFlow
WORKDIR ${TF_BUILD_PATH}
RUN bazel build -c opt //tensorflow/tools/pip_package:build_pip_package
WORKDIR ${TF_BUILD_PATH}
RUN bazel-bin/tensorflow/tools/pip_package/build_pip_package ${TF_BUILD_OUTPUT} && pip install --no-cache-dir ${TF_BUILD_OUTPUT}/tensorflow-*.whl
RUN pip install --no-cache-dir keras==2.6

# Download and extract cifar-10 dataset
WORKDIR /hfl-tensorflow
COPY hfl-tensorflow /hfl-tensorflow
RUN wget -q https://www.cs.toronto.edu/~kriz/cifar-10-binary.tar.gz && tar -xvzf cifar-10-binary.tar.gz

COPY sgx_default_qcnl.conf /etc/sgx_default_qcnl.conf
COPY azure/azure_tdx_config.json /etc
COPY luks_tools /luks_tools

# Disable apport
RUN echo "enabled=0" > /etc/default/apport \
    && echo "exit 0" > /usr/sbin/policy-rc.d

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/pip/* \
    && rm -rf /tmp/*

WORKDIR /
