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

# https://github.com/oscarlab/graphene/blob/master/Tools/gsc/images/graphene_aks.latest.dockerfile

ARG BASE_IMAGE=ubuntu:20.04
FROM ${BASE_IMAGE}

# Optional build argument to select a build for Azure
ARG AZURE

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

# Intel SGX
RUN wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add - \
    && apt-get update

# Install SGX-PSW
RUN apt-get install -y libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-quote-ex-dev libsgx-qe3-logic sgx-aesm-service

# Install SGX-DCAP
RUN apt-get install -y libsgx-dcap-ql-dev libsgx-dcap-quote-verify-dev

# Install SGX-DCAP quote provider library
RUN if [ -z "$AZURE" ]; then \
        # Not a build for Azure, so install the default quote provider library \
        apt-get install -y libsgx-dcap-default-qpl libsgx-dcap-default-qpl-dev; \
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

RUN apt-get install -y gawk bison python3-click python3-jinja2 golang ninja-build \ 
    libcurl4-openssl-dev libprotobuf-c-dev python3-protobuf protobuf-c-compiler \ 
    libgmp-dev libmpfr-dev libmpc-dev libisl-dev nasm

RUN ln -s /usr/bin/python3 /usr/bin/python \
    && pip3 install --upgrade pip \
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

RUN gramine-sgx-gen-private-key

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

RUN pip3 install --upgrade pip setuptools==44.1.1

# bazel
ENV BAZEL_VERSION=3.1.0
RUN wget "https://github.com/bazelbuild/bazel/releases/download/${BAZEL_VERSION}/bazel_${BAZEL_VERSION}-linux-x86_64.deb" \
 && dpkg -i bazel_*.deb

# deps 
RUN pip3 install numpy keras_preprocessing pandas sklearn matplotlib

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
RUN cd ${TF_BUILD_PATH} && ./build.sh ubuntu
RUN cd ${TF_BUILD_PATH} && bazel build -c opt //tensorflow/tools/pip_package:build_pip_package
RUN cd ${TF_BUILD_PATH} && bazel-bin/tensorflow/tools/pip_package/build_pip_package ${TF_BUILD_OUTPUT} && pip install ${TF_BUILD_OUTPUT}/tensorflow-*.whl

COPY patches/sgx_default_qcnl.conf /etc

# disable apport
RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

# Build argument to select a workload
ARG WORKLOAD

COPY image_classification /image_classification
COPY recommendation_system /recommendation_system

RUN if [ "${BASE_IMAGE}" = "ubuntu:18.04" ]; then \
    cd /image_classification && \
    sed -i "41s/# //" python.manifest.template && \
    sed -i "42s/^/#/" python.manifest.template && \
    sed -i "65s/# //" python.manifest.template && \
    sed -i "66s/^/#/" python.manifest.template && \
    cd ../recommendation_system && \
    sed -i "41s/# //" python.manifest.template && \
    sed -i "42s/^/#/" python.manifest.template && \
    sed -i "65s/# //" python.manifest.template && \
    sed -i "66s/^/#/" python.manifest.template; \
    fi

ARG BASE_IMAGE=ubuntu:20.04
RUN if [ "${BASE_IMAGE}" = "ubuntu:20.04" ] ; then \
    python -m pip install markupsafe==2.0.1 && pip install numpy --upgrade; \
    fi

RUN if [ "$WORKLOAD" = "image_classification" ]; then \
    # prepare cifar-10 dataset and make image classification project \
	cd /image_classification && wget https://www.cs.toronto.edu/~kriz/cifar-10-binary.tar.gz && tar -xvzf cifar-10-binary.tar.gz \
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
