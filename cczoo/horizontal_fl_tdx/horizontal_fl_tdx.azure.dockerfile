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
RUN add-apt-repository ppa:team-xbmc/ppa -y

RUN apt-get update && apt-get install -y --no-install-recommends \
        apt-utils \
        ca-certificates \
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
        libcurl4-openssl-dev libprotobuf-c-dev python3-protobuf protobuf-c-compiler protobuf-compiler\
        libgmp-dev libmpfr-dev libmpc-dev libisl-dev nasm \
        expect cryptsetup e2fsprogs python3-dev \
# Install SGX PSW
        libsgx-ae-qve libtdx-attest libtdx-attest-dev tdx-qgs libsgx-urts \
# Install SGX DCAP
        libsgx-dcap-quote-verify libsgx-dcap-quote-verify-dev \
# Install dependencies for Azure DCAP Client
        libssl-dev libcurl4-openssl-dev pkg-config nlohmann-json3-dev \
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

WORKDIR /opt/intel
RUN wget -q https://download.01.org/intel-sgx/sgx-dcap/1.15/linux/distro/ubuntu20.04-server/sgx_linux_x64_sdk_2.18.100.3.bin
COPY sgx_sdk_install.sh .
RUN chmod +x sgx_linux_x64_sdk_2.18.100.3.bin
RUN ./sgx_sdk_install.sh
RUN . /opt/intel/sgxsdk/environment

RUN ln -s /usr/bin/python3 /usr/bin/python \
    && pip3 install --no-cache-dir --upgrade \
        'pip>=23.1.2' 'wheel>=0.38.0' 'toml>=0.10.2' 'meson>=1.1.1' 'setuptools>=45.2.0' \
        'numpy==1.19.5' 'keras_preprocessing>=1.1.2' 'pandas==1.1.5' 'scikit-learn>=0.0.post5' 'matplotlib==3.3.4'

# bazel
RUN wget -q https://github.com/bazelbuild/bazel/releases/download/3.7.2/bazel-3.7.2-installer-linux-x86_64.sh
RUN bash bazel-3.7.2-installer-linux-x86_64.sh && echo "source /usr/local/lib/bazel/bin/bazel-complete.bash" >> ~/.bashrc

ARG MBEDTLS_VERSION=2.26.0
RUN wget -q https://github.com/Mbed-TLS/mbedtls/archive/refs/tags/v${MBEDTLS_VERSION}.tar.gz \
    && tar -zxvf v${MBEDTLS_VERSION}.tar.gz \
    && cp -r mbedtls-${MBEDTLS_VERSION}/include/mbedtls ${INSTALL_PREFIX}/include

# config and download TensorFlow
ENV TF_VERSION=v2.6.0
ENV TF_BUILD_PATH=/tf/src
ENV TF_BUILD_OUTPUT=/tf/output
RUN git clone  --recurse-submodules -b ${TF_VERSION} https://github.com/tensorflow/tensorflow ${TF_BUILD_PATH}

# git apply diff
COPY tf_v2.6.diff_azure ${TF_BUILD_PATH}
COPY grpc_ratls.patch ${TF_BUILD_PATH}/third_party/grpc/
WORKDIR ${TF_BUILD_PATH}
RUN git apply tf_v2.6.diff_azure

ENV SGX_RA_TLS_BACKEND=TDX

# build and install TensorFlow
WORKDIR ${TF_BUILD_PATH}
RUN bazel build -c opt //tensorflow/tools/pip_package:build_pip_package
WORKDIR ${TF_BUILD_PATH}
RUN bazel-bin/tensorflow/tools/pip_package/build_pip_package ${TF_BUILD_OUTPUT} && pip install --no-cache-dir ${TF_BUILD_OUTPUT}/tensorflow-*.whl
RUN pip install --no-cache-dir keras==2.6

# download and exact cifar-10 dataset
WORKDIR /hfl-tensorflow
COPY hfl-tensorflow /hfl-tensorflow
RUN wget -q https://www.cs.toronto.edu/~kriz/cifar-10-binary.tar.gz && tar -xvzf cifar-10-binary.tar.gz

COPY sgx_default_qcnl.conf /etc/sgx_default_qcnl.conf
COPY luks_tools /luks_tools

# disable apport
RUN echo "enabled=0" > /etc/default/apport \
    && echo "exit 0" > /usr/sbin/policy-rc.d

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/pip/* \
    && rm -rf /tmp/*

WORKDIR /
