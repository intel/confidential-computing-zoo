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

# https://github.com/oscarlab/graphene/blob/master/Tools/gsc/images/graphene_aks.latest.dockerfile

FROM ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}

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

# Intel SGX
RUN echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu bionic main" | tee /etc/apt/sources.list.d/intel-sgx.list \
    && wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add - \
    && apt-get update

# Install SGX-PSW
RUN apt-get install -y libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-quote-ex-dev libsgx-qe3-logic sgx-aesm-service

# Install SGX-DCAP
RUN apt-get install -y libsgx-dcap-ql-dev libsgx-dcap-default-qpl libsgx-dcap-quote-verify-dev libsgx-dcap-default-qpl-dev

# Gramine
ENV GRAMINEDIR=/gramine
ENV SGX_DCAP_VERSION=DCAP_1.11
ENV GRAMINE_VERSION=c662f63bba76736e6d5122a866da762efd1978c1
ENV ISGX_DRIVER_PATH=${GRAMINEDIR}/driver
ENV SGX_SIGNER_KEY=${GRAMINEDIR}/Pal/src/host/Linux-SGX/signer/enclave-key.pem
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8
ENV WERROR=1
ENV SGX=1

RUN apt-get install -y gawk bison python3-click python3-jinja2 golang ninja-build
RUN apt-get install -y libcurl4-openssl-dev libprotobuf-c-dev python3-protobuf protobuf-c-compiler
RUN apt-get install -y libgmp-dev libmpfr-dev libmpc-dev libisl-dev

RUN ln -s /usr/bin/python3 /usr/bin/python \
    && pip3 install --upgrade pip \
    && pip3 install toml meson

RUN git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && cd ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && cd ${ISGX_DRIVER_PATH} \
    && git checkout ${SGX_DCAP_VERSION}

COPY patches/gramine/patches ${GRAMINEDIR}
RUN cd ${GRAMINEDIR} \
    && git apply *.diff

RUN openssl genrsa -3 -out ${SGX_SIGNER_KEY} 3072
RUN cd ${GRAMINEDIR} \
    && LD_LIBRARY_PATH="" meson setup build/ --buildtype=debug -Dprefix=${INSTALL_PREFIX} -Ddirect=enabled -Dsgx=enabled -Ddcap=enabled -Dsgx_driver=dcap1.10 -Dsgx_driver_include_path=${ISGX_DRIVER_PATH}/driver/linux/include \
    && LD_LIBRARY_PATH="" ninja -C build/ \
    && LD_LIBRARY_PATH="" ninja -C build/ install

# Install mbedtls
RUN cd ${GRAMINEDIR}/build/subprojects/mbedtls-mbedtls* \
    && cp -r `find . -name "*_gramine.a"` ${INSTALL_PREFIX}/lib \
    && cp -r ${GRAMINEDIR}/subprojects/mbedtls-mbedtls*/include ${INSTALL_PREFIX}

# Install cJSON
RUN cd ${GRAMINEDIR}/subprojects/cJSON* \
    && make static \
    && cp -r *.a ${INSTALL_PREFIX}/lib \
    && mkdir -p ${INSTALL_PREFIX}/include/cjson \
    && cp -r *.h ${INSTALL_PREFIX}/include/cjson

RUN pip3 install --upgrade pip setuptools==44.1.1

# bazel
ENV BAZEL_VERSION=3.1.0
RUN wget "https://github.com/bazelbuild/bazel/releases/download/${BAZEL_VERSION}/bazel_${BAZEL_VERSION}-linux-x86_64.deb" \
 && dpkg -i bazel_*.deb

# deps 
RUN pip3 install numpy keras_preprocessing 

# config and download TensorFlow
ENV TF_VERSION=v2.4.2
ENV TF_BUILD_PATH=/tf/src
ENV TF_BUILD_OUTPUT=/tf/output
RUN git clone  --recurse-submodules -b ${TF_VERSION} https://github.com/tensorflow/tensorflow ${TF_BUILD_PATH}

# Prepare build source code
COPY patches/gramine ${GRAMINEDIR}

# git apply diff
COPY patches/tf ${TF_BUILD_PATH} 
RUN cd ${TF_BUILD_PATH} && git apply tf2_4.diff

# build and install TensorFlow
RUN cd ${TF_BUILD_PATH} && ./build.sh
RUN cd ${TF_BUILD_PATH} && bazel build -c opt //tensorflow/tools/pip_package:build_pip_package
RUN cd ${TF_BUILD_PATH} && bazel-bin/tensorflow/tools/pip_package/build_pip_package ${TF_BUILD_OUTPUT} && pip install ${TF_BUILD_OUTPUT}/tensorflow-*-cp36-cp36m-linux_x86_64.whl

# aesm service
COPY patches/sgx_default_qcnl.conf /etc
COPY patches/start_aesm_service.sh /

# download and exact cifar-10 dataset
RUN mkdir /hfl-tensorflow
COPY hfl-tensorflow /hfl-tensorflow
RUN cd /hfl-tensorflow && wget https://www.cs.toronto.edu/~kriz/cifar-10-binary.tar.gz && tar -xvzf cifar-10-binary.tar.gz

# disable apport
RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

# make project
RUN cd /hfl-tensorflow && test-sgx.sh make

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/pip/* \
    && rm -rf /tmp/*

EXPOSE 6006 50051 50052
