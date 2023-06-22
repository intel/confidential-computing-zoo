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
RUN ["/bin/bash", "-c", "set -o pipefail && echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections"]

# Add steps here to set up dependencies
# Add steps here to set up dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget \
        curl \
        gnupg \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN ["/bin/bash", "-c", "set -o pipefail && echo 'deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main' | tee /etc/apt/sources.list.d/intel-sgx.list"]
RUN ["/bin/bash", "-c", "set -o pipefail && curl https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add -"]

# Add TensorFlow Serving distribution URI as a package source
# Specify 2.8.0 which is the latest version compatible with the glibc version in Ubuntu 18.04
RUN ["/bin/bash", "-c", "set -o pipefail && echo 'deb [trusted=yes arch=amd64] http://storage.googleapis.com/tensorflow-serving-apt testing tensorflow-model-server-2.8.0' | tee /etc/apt/sources.list.d/tensorflow-serving.list"]
RUN ["/bin/bash", "-c", "set -o pipefail && curl https://storage.googleapis.com/tensorflow-serving-apt/tensorflow-serving.release.pub.gpg | apt-key add -"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
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
        nasm \
        software-properties-common \
        apt-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1
RUN python3 -B -m pip install --no-cache-dir \
    'wheel>=0.38.0' \
    'toml>=0.10' \
    'meson>=0.55' \
    'cryptography>=41.0.1' \
    'pyelftools>=0.29'

# Install SGX PSW
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-qe3-logic sgx-aesm-service \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install SGX DCAP
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libsgx-dcap-ql-dev libsgx-dcap-quote-verify-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install SGX-DCAP quote provider library
# Build for Azure, so install the Azure DCAP Client (Release 1.10.0) \
RUN add-apt-repository ppa:team-xbmc/ppa -y \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libssl-dev libcurl4-openssl-dev pkg-config nlohmann-json3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /azure
ARG AZUREDIR=/azure
RUN git clone https://github.com/microsoft/Azure-DCAP-Client ${AZUREDIR} \
    && git checkout 1.10.0 \
    &&git submodule update --recursive --init

WORKDIR /azure/src/Linux
RUN ./configure \
    && make DEBUG=1 \
    && make install \
    && cp libdcap_quoteprov.so /usr/lib/x86_64-linux-gnu/

# Clone Gramine and Init submodules
# dimakuv/ra-tls-maa
WORKDIR ${GRAMINEDIR}
ARG GRAMINE_VERSION=a2166216fd795adfa7391be7fb6398116c317ee3
RUN git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

# Create SGX driver for header files
WORKDIR ${ISGX_DRIVER_PATH}
RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && git checkout DCAP_1.11

# Build Gramine
WORKDIR ${GRAMINEDIR}
RUN pwd && meson setup build/ --buildtype=release -Dsgx=enabled -Ddcap=enabled -Dsgx_driver="dcap1.10" -Dsgx_driver_include_path="/gramine/driver/driver/linux/include" \
    && ninja -C build/ \
    && ninja -C build/ install
RUN gramine-sgx-gen-private-key

ARG TF_SERVING_PKGNAME=tensorflow-model-server
ARG TF_SERVING_VERSION=2.6.2
RUN curl -LO https://storage.googleapis.com/tensorflow-serving-apt/pool/${TF_SERVING_PKGNAME}-${TF_SERVING_VERSION}/t/${TF_SERVING_PKGNAME}/${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb \
    && apt-get install -y --no-install-recommends ./${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb

# Build Secret Provision
ENV RA_TYPE=maa
WORKDIR ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov
RUN make app ${RA_TYPE} RA_TYPE=${RA_TYPE}

COPY ca.crt ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov/ssl

WORKDIR ${WORK_BASE_PATH}

RUN cp ${GRAMINEDIR}/build/tools/sgx/ra-tls/libsecret_prov_attest.so . \
    && cp -R ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov/ssl .

COPY Makefile .
COPY tensorflow_model_server.manifest.template .
RUN make SGX=${SGX} RA_TYPE=${RA_TYPE} -j "$(nproc)" | grep "mr_enclave\|mr_signer\|isv_prod_id\|isv_svn" | tee -a enclave.mr

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
