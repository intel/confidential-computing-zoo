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

# Use TDX base Docker image
ARG BASE_IMAGE=intelcczoo/tdx-dev:dcap_mvp2023ww15-ubuntu22.04-latest
FROM ${BASE_IMAGE}

# Install apt deps
RUN apt update && apt install -y vim unzip curl build-essential zlib1g-dev libncurses5-dev \
    libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget python3-distutils

# Install Python3.8
RUN wget https://www.python.org/ftp/python/3.8.12/Python-3.8.12.tgz \
    && tar -xzvf Python-3.8.12.tgz \
    && cd Python-3.8.12 \
    && ./configure --enable-optimizations \
    && make \
    && make install \
    && update-alternatives --install /usr/bin/python3 python3 /usr/local/bin/python3.8 1

# Install bazel
RUN curl -fSsL -O https://github.com/bazelbuild/bazel/releases/download/3.7.2/bazel-3.7.2-installer-linux-x86_64.sh
RUN bash bazel-3.7.2-installer-linux-x86_64.sh && echo "source /usr/local/lib/bazel/bin/bazel-complete.bash" >> ~/.bashrc

# Install Python deps
RUN pip3 install numpy==1.23.5 keras==2.6 keras_preprocessing pandas sklearn matplotlib wheel

# Install mbedtls
ARG MBEDTLS_VERSION=2.26.0
RUN wget https://github.com/Mbed-TLS/mbedtls/archive/refs/tags/v${MBEDTLS_VERSION}.tar.gz \
    && tar -zxvf v${MBEDTLS_VERSION}.tar.gz \
    && cp -r mbedtls-${MBEDTLS_VERSION}/include/mbedtls ${INSTALL_PREFIX}/include

# Config and download TensorFlow
ENV TF_VERSION=v2.6.0
ENV TF_BUILD_PATH=/tf/src
ENV TF_BUILD_OUTPUT=/tf/output
RUN git clone  --recurse-submodules -b ${TF_VERSION} https://github.com/tensorflow/tensorflow ${TF_BUILD_PATH}

# Apply the TF patch
COPY tf_v2.6.diff ${TF_BUILD_PATH}
COPY grpc_ratls.patch ${TF_BUILD_PATH}/third_party/grpc/
RUN cd ${TF_BUILD_PATH} && git apply tf_v2.6.diff

# Use TDX as the RA backend
ENV SGX_RA_TLS_BACKEND=TDX

# Build and install TensorFlow
RUN cd ${TF_BUILD_PATH} && bazel build -c opt //tensorflow/tools/pip_package:build_pip_package
RUN cd ${TF_BUILD_PATH} && bazel-bin/tensorflow/tools/pip_package/build_pip_package ${TF_BUILD_OUTPUT} && pip install ${TF_BUILD_OUTPUT}/tensorflow*.whl
RUN apt-get install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget

# Download and exact cifar-10 dataset
RUN mkdir /hfl-tensorflow
COPY hfl-tensorflow /hfl-tensorflow
RUN cd /hfl-tensorflow && wget https://www.cs.toronto.edu/~kriz/cifar-10-binary.tar.gz && tar -xvzf cifar-10-binary.tar.gz

COPY sgx_default_qcnl.conf /etc/sgx_default_qcnl.conf
COPY luks_tools /luks_tools

# Disable apport
RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d
