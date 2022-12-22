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

# Optional build argument to select a build for Azure
ARG AZURE

ENV GRAMINEDIR=/gramine
ENV ISGX_DRIVER_PATH=${GRAMINEDIR}/driver
ENV WORK_BASE_PATH=${GRAMINEDIR}/CI-Examples/tensorflow-serving-cluster/tensorflow-serving
ENV MODEL_BASE_PATH=${WORK_BASE_PATH}/models
ENV MODEL_NAME=model
ENV WERROR=1
ENV SGX=1
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8


# Enable it to disable debconf warning
RUN echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections

# Add steps here to set up dependencies
RUN apt-get update \
    && apt-get install -y \
        autoconf \
        bison \
        build-essential \
        coreutils \
        gawk \
        git \
        golang \
        libcurl4-openssl-dev \
        libprotobuf-c-dev \
        protobuf-c-compiler \
        protobuf-compiler \
        python3.7 \
        python3-protobuf \
        python3-pip \
        python3-dev \
        python3-click \
        python3-jinja2 \
        libnss-mdns \
        libnss-myhostname \
        libcurl4-openssl-dev \
        libprotobuf-c-dev \
        lsb-release \
        ninja-build \
        wget \
        curl \
        nasm \
    && apt-get install -y --no-install-recommends apt-utils

# Install SGX-DCAP quote provider library
RUN if [ ! -z "$AZURE" ]; then \
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

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1
RUN python3 -B -m pip install 'toml>=0.10' 'meson>=0.55' cryptography pyelftools

RUN echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main" | tee /etc/apt/sources.list.d/intel-sgx.list \
    && wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add -

RUN apt-get update

# Add TensorFlow Serving distribution URI as a package source
# Specify 2.8.0 which is the latest version compatible with the glibc version in Ubuntu 18.04
RUN echo "deb [trusted=yes arch=amd64] http://storage.googleapis.com/tensorflow-serving-apt testing tensorflow-model-server-2.8.0" | tee /etc/apt/sources.list.d/tensorflow-serving.list \
    && curl https://storage.googleapis.com/tensorflow-serving-apt/tensorflow-serving.release.pub.gpg | apt-key add -

RUN apt-get update

# Install SGX PSW
RUN apt-get install -y libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-qe3-logic sgx-aesm-service

# Install DCAP
RUN apt-get install -y libsgx-dcap-ql-dev libsgx-dcap-quote-verify-dev

# Install SGX-DCAP quote provider library
RUN if [ -z "$AZURE" ]; then \
        # Not a build for Azure, so install the default quote provider library \
        apt-get install -y libsgx-dcap-default-qpl; \
    fi

# Clone Gramine and Init submodules
RUN git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && cd ${GRAMINEDIR} \
    && git checkout v1.3.1


# Create SGX driver for header files
RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && cd ${ISGX_DRIVER_PATH} \
    && git checkout DCAP_1.11

# Build Gramine
RUN cd ${GRAMINEDIR} && pwd && meson setup build/ --buildtype=release -Dsgx=enabled -Ddcap=enabled -Dsgx_driver="dcap1.10" -Dsgx_driver_include_path="/gramine/driver/driver/linux/include" \
    && ninja -C build/ \
    && ninja -C build/ install
RUN gramine-sgx-gen-private-key

# Install the latest tensorflow-model-server
# RUN apt-cache madison "tensorflow-model-server"
# RUN apt-get install -y tensorflow-model-server

ARG TF_SERVING_PKGNAME=tensorflow-model-server
ARG TF_SERVING_VERSION=2.6.2
RUN curl -LO https://storage.googleapis.com/tensorflow-serving-apt/pool/${TF_SERVING_PKGNAME}-${TF_SERVING_VERSION}/t/${TF_SERVING_PKGNAME}/${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb \
    && apt-get install -y ./${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb


# Clean apt cache
RUN apt-get clean all

# Build Secret Provision
RUN cd ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov \
    && make app dcap RA_TYPE=dcap

COPY ca.crt ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov/ssl

WORKDIR ${WORK_BASE_PATH}

RUN cp ${GRAMINEDIR}/build/tools/sgx/ra-tls/libsecret_prov_attest.so . \
    && cp -R ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov/ssl . 

COPY Makefile .
COPY tensorflow_model_server.manifest.template .
COPY tf_serving_entrypoint.sh /usr/bin
COPY sgx_default_qcnl.conf /etc/sgx_default_qcnl.conf

# Expose tensorflow-model-server ports
# gRPC
EXPOSE 8500
# REST
EXPOSE 8501

RUN chmod +x /usr/bin/tf_serving_entrypoint.sh
RUN cat /etc/sgx_default_qcnl.conf
ENTRYPOINT ["/usr/bin/tf_serving_entrypoint.sh"]

