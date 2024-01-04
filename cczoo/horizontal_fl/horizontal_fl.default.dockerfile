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
        pkg-config \
        gawk bison python3-click python3-jinja2 golang ninja-build \
        libcurl4-openssl-dev libprotobuf-c-dev python3-protobuf protobuf-c-compiler protobuf-compiler\
        libgmp-dev libmpfr-dev libmpc-dev libisl-dev nasm \
# Install SGX PSW
        libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-quote-ex-dev libsgx-qe3-logic sgx-aesm-service \
# Install SGX DCAP
        libsgx-dcap-ql-dev libsgx-dcap-quote-verify-dev libsgx-dcap-default-qpl libsgx-dcap-default-qpl-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Gramine
ENV GRAMINEDIR=/gramine
ENV SGX_DCAP_VERSION=DCAP_1.11
ENV GRAMINE_VERSION=v1.3.1
ENV ISGX_DRIVER_PATH=${GRAMINEDIR}/driver
ENV WERROR=1
ENV SGX=1

RUN ln -s /usr/bin/python3 /usr/bin/python \
    && pip3 install --no-cache-dir --upgrade \
        'pip>=23.1.2' 'wheel>=0.38.0' 'toml>=0.10' 'meson>=0.55' 'cryptography>=41.0.1' 'pyelftools>=0.29' 'setuptools==44.1.1' \
        'numpy==1.23.5' 'keras_preprocessing>=1.1.2' 'pandas==1.5.2' 'scikit-learn==1.1.3' 'matplotlib>=3.7.1'

WORKDIR ${GRAMINEDIR}
RUN git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

WORKDIR ${ISGX_DRIVER_PATH}
RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && git checkout ${SGX_DCAP_VERSION}

WORKDIR ${GRAMINEDIR}
RUN LD_LIBRARY_PATH="" meson setup build/ --buildtype=debug -Dprefix=${INSTALL_PREFIX} -Ddirect=enabled -Dsgx=enabled -Ddcap=enabled -Dsgx_driver=dcap1.10 -Dsgx_driver_include_path=${ISGX_DRIVER_PATH}/driver/linux/include \
    && LD_LIBRARY_PATH="" ninja -C build/ \
    && LD_LIBRARY_PATH="" ninja -C build/ install

RUN gramine-sgx-gen-private-key

# Install mbedtls
WORKDIR ${GRAMINEDIR}/build/subprojects/mbedtls-mbedtls-3.2.1
RUN cp -r ./*_gramine.a ${INSTALL_PREFIX}/lib
WORKDIR ${GRAMINEDIR}/subprojects/mbedtls-mbedtls-3.2.1/mbedtls-mbedtls-3.2.1
RUN cp -r include/mbedtls ${INSTALL_PREFIX}/include

# Install cJSON
WORKDIR ${GRAMINEDIR}/subprojects/cJSON-1.7.12
RUN make static \
    && cp -r ./*.a ${INSTALL_PREFIX}/lib \
    && mkdir -p ${INSTALL_PREFIX}/include/cjson \
    && cp -r ./*.h ${INSTALL_PREFIX}/include/cjson

# bazel
ENV BAZEL_VERSION=3.1.0
RUN wget -q "https://github.com/bazelbuild/bazel/releases/download/${BAZEL_VERSION}/bazel_${BAZEL_VERSION}-linux-x86_64.deb" \
 && dpkg -i bazel_*.deb

# config and download TensorFlow
ENV TF_VERSION=v2.4.2
ENV TF_BUILD_PATH=/tf/src
ENV TF_BUILD_OUTPUT=/tf/output
RUN git clone  --recurse-submodules -b ${TF_VERSION} https://github.com/tensorflow/tensorflow ${TF_BUILD_PATH}

# Prepare build source code
COPY patches/gramine ${GRAMINEDIR}

# git apply diff
COPY patches/tf ${TF_BUILD_PATH}
WORKDIR ${TF_BUILD_PATH}
RUN git apply tf2_4.diff

# build and install TensorFlow
WORKDIR ${TF_BUILD_PATH}
RUN ./build.sh ubuntu
WORKDIR ${TF_BUILD_PATH}
RUN bazel build -c opt //tensorflow/tools/pip_package:build_pip_package
WORKDIR ${TF_BUILD_PATH}
RUN bazel-bin/tensorflow/tools/pip_package/build_pip_package ${TF_BUILD_OUTPUT} && pip install --no-cache-dir ${TF_BUILD_OUTPUT}/tensorflow-*.whl

COPY patches/sgx_default_qcnl.conf /etc

# disable apport
RUN echo "enabled=0" > /etc/default/apport \
    && echo "exit 0" > /usr/sbin/policy-rc.d

# Build argument to select a workload
ARG WORKLOAD

COPY image_classification /image_classification
COPY recommendation_system /recommendation_system

RUN python -m pip install --no-cache-dir markupsafe==2.0.1 && pip install --no-cache-dir numpy==1.23.5 --upgrade;

RUN if [ "$WORKLOAD" = "image_classification" ]; then \
    # prepare cifar-10 dataset and make image classification project \
	cd /image_classification && wget -q https://www.cs.toronto.edu/~kriz/cifar-10-binary.tar.gz && tar -xvzf cifar-10-binary.tar.gz \
	&& test-sgx.sh make; \
    elif [ "$WORKLOAD" = "recommendation_system" ]; then \
    # prepare dataset and make recommendation system project \
	cd /recommendation_system/dataset && tar -zxvf train.tar && cd .. && test-sgx.sh make; \
    else \
    echo "Please choose correct workload: image_classification or recommendation_system." \
	&& exit 1; \
    fi

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/pip/* \
    && rm -rf /tmp/*

WORKDIR /
