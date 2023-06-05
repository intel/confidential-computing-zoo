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

FROM ubuntu:20.04

ARG http_proxy
ENV DEBIAN_FRONTEND=nointeractive
ENV HOMO_LR_DIR=/homo_lr
ENV GRAMINEDIR=$HOMO_LR_DIR/gramine
ENV ISGX_DRIVER_PATH=${GRAMINEDIR}/driver
ENV SGX_SIGNER_KEY=${GRAMINEDIR}/Pal/src/host/Linux-SGX/signer/enclave-key.pem
ENV SGX=1
ENV IPCL_PY_DIR=ipcl-python
ENV PYTHONPATH=/homo_lr/glade-phe/build/python:/homo_lr/glade-phe/python:$PYTHONPATH
ENV http_proxy=$http_proxy
ENV https_proxy=$http_proxy

RUN apt-get update \
    && apt-get install -y \
        autoconf \
        bison \
        build-essential \
        coreutils \
        gawk \
        git \
        libcurl4-openssl-dev \
        libssl-dev \
        libprotobuf-c-dev \
        protobuf-c-compiler \
        python3-protobuf \
        python3-pip \
        python3-dev \
        lsb-release \
        wget \
        curl \
        init \
        nasm \
        ninja-build \
        pkg-config \
        libpthread-stubs0-dev \
        libnuma-dev \
        libmpfr-dev \
        libmpc-dev \
    && apt-get install -y --no-install-recommends apt-utils

RUN pip3 install numpy gmpy2 grpcio pandas jinja2 grpcio_tools click cryptography 'toml>=0.10' 'meson>=0.55'

RUN echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main" | tee /etc/apt/sources.list.d/intel-sgx.list \
    && wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add -
RUN apt-get update
# Install SGX PSW
RUN apt-get install -y libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-qe3-logic sgx-aesm-service
# Install DCAP
RUN apt-get install -y libsgx-dcap-ql-dev libsgx-dcap-default-qpl libsgx-dcap-quote-verify-dev

# Clone Gramine and Init submodules
RUN git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && cd ${GRAMINEDIR} \
    && git checkout v1.2
# Create SGX driver for header files
RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && cd ${ISGX_DRIVER_PATH} \
    && git checkout DCAP_1.11

# Build Gramine
RUN cd ${GRAMINEDIR} && pwd && meson setup build/ --buildtype=debug -Dsgx=enabled -Ddcap=enabled -Dsgx_driver="dcap1.10" -Dsgx_driver_include_path="/homo_lr/gramine/driver/driver/linux/include" \
    && ninja -C build/ \
    && ninja -C build/ install

RUN gramine-sgx-gen-private-key

# Build Secret Provision
RUN cd ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov \
    && make dcap

RUN cp ${GRAMINEDIR}/build/Pal/src/host/Linux-SGX/tools/ra-tls/libsecret_prov_attest.so .

# Install cmake
RUN wget http://cmake.org/files/v3.22/cmake-3.22.0.tar.gz \
    && tar xzvf cmake-3.22.0.tar.gz \
    && cd cmake-3.22.0 \
    && ./configure \
    && make install -j

WORKDIR $HOMO_LR_DIR

COPY *.csv homo_lr_ps.py homo_lr_worker.py homo_lr.proto \
    Makefile homo_lr.manifest.template \
    0001-disable-openmp.patch ./
COPY sgx_default_qcnl.conf /etc/sgx_default_qcnl.conf

# IPCL Python Wrapper
RUN git clone -b v1.1.3 https://github.com/intel/pailliercryptolib_python.git $IPCL_PY_DIR \
    && cd $IPCL_PY_DIR \
    && patch -p1 < ../0001-disable-openmp.patch \
    && python3 setup.py install \
    && cd -

# Generate Grpc proto file
RUN python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. homo_lr.proto

# Build gramine sgx manifest
RUN make SGX=1 -j

# Clean apt cache
RUN apt-get clean all

ENV http_proxy=
ENV https_proxy=
