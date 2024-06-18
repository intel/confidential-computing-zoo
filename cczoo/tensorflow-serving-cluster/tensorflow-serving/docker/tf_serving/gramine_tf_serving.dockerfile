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
ENV SGX_SIGNER_KEY=/root/.config/gramine/enclave-key.pem
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
# For Gramine RA-TLS
ENV PYTHONDONTWRITEBYTECODE=1
ENV RA_TYPE=dcap

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

# Install SGX DCAP
RUN apt-get install -y libsgx-dcap-ql-dev libsgx-dcap-default-qpl libsgx-dcap-quote-verify-dev

# Clone Gramine and Init submodules
ARG GRAMINE_VERSION=devel-v1.3.1-2023-07-13
RUN git clone https://github.com/analytics-zoo/gramine ${GRAMINEDIR} \
    && cd ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

# Create SGX driver for header files
RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && cd ${ISGX_DRIVER_PATH} \
    && git checkout DCAP_1.11

COPY sgx/gramine/patches ${GRAMINEDIR}
RUN cd ${GRAMINEDIR} \
    && git apply *.diff


# Build Gramine
RUN mkdir -p /root/.config/gramine/ && openssl genrsa -3 -out ${SGX_SIGNER_KEY} 3072
RUN cd ${GRAMINEDIR} \
    && LD_LIBRARY_PATH="" meson setup build/ --buildtype=release -Dprefix=${INSTALL_PREFIX} -Ddirect=enabled -Dsgx=enabled -Ddcap=enabled -Dsgx_driver=dcap1.10 -Dsgx_driver_include_path=${ISGX_DRIVER_PATH}/driver/linux/include \
    && LD_LIBRARY_PATH="" ninja -C build/ \
    && LD_LIBRARY_PATH="" ninja -C build/ install

# Install mbedtls
RUN cd ${GRAMINEDIR}/build/subprojects/mbedtls-mbedtls* \
    && cp -r `find . -maxdepth 1 -name "*_gramine.a"` ${INSTALL_PREFIX}/lib \
    && cp -r ${GRAMINEDIR}/subprojects/mbedtls-mbedtls*/mbedtls-mbedtls*/include ${INSTALL_PREFIX}

# Install the latest tensorflow-model-server
 RUN apt-cache madison "tensorflow-model-server"
 RUN apt-get install -y tensorflow-model-server

ARG TF_SERVING_PKGNAME=tensorflow-model-server
ARG TF_SERVING_VERSION=2.6.2
RUN curl -LO https://storage.googleapis.com/tensorflow-serving-apt/pool/${TF_SERVING_PKGNAME}-${TF_SERVING_VERSION}/t/${TF_SERVING_PKGNAME}/${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb \
    && apt-get install -y ./${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb --allow-downgrades

# Clean apt cache
RUN apt-get clean all

# Build Secret Provision
RUN cd ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov \
    && make app dcap RA_TYPE=dcap

# COPY ca.crt ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov/ssl

WORKDIR ${WORK_BASE_PATH}

#RUN cp ${GRAMINEDIR}/build/tools/sgx/ra-tls/libsecret_prov_attest.so . \
#    && cp -R ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov/ssl .

RUN mkdir -p ${WORK_BASE_PATH}/ssl
COPY ssl/ca.crt ${WORK_BASE_PATH}/ssl
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

RUN make SGX=${SGX} RA_TYPE=dcap  | grep "mr_enclave\|mr_signer\|isv_prod_id\|isv_svn" | tee -a enclave.mr

ENTRYPOINT ["/usr/bin/tf_serving_entrypoint.sh"]
