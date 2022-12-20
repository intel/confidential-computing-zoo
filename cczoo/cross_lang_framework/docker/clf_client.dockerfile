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

#---------------------------------------------
# Install SGX environment
# (adjust based on gramine-sgx-dev.dockerfile)
#---------------------------------------------
ARG base_image=ubuntu:20.04
FROM ${base_image}

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8

# Add steps here to set up dependencies (check gramine dependence)
RUN apt-get update \
    && apt-get install -y --no-install-recommends apt-utils \
    && apt-get install -y \
        ca-certificates build-essential libtool python3-dev \
        git zlib1g-dev unzip vim jq gdb musl-tools \
        autoconf bison gawk nasm ninja-build python3 python3-click \
        python3-jinja2 python3-pyelftools wget \
        libcurl4-openssl-dev \
        libprotobuf-c-dev protobuf-c-compiler protobuf-compiler \
        python3-cryptography python3-pip python3-protobuf

ARG BASE_IMAGE=ubuntu:20.04
RUN if [ "${BASE_IMAGE}" = "ubuntu:18.04" ] ; then \
        echo "use ubuntu:18.04 as base image" ; \
        echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu bionic main" | tee /etc/apt/sources.list.d/intel-sgx.list ; \
    elif [ "${BASE_IMAGE}" = "ubuntu:20.04" ] ; then \
        echo "use ubuntu:20.04 as base image" ; \
        echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main" | tee /etc/apt/sources.list.d/intel-sgx.list ; \
    else \
        echo "wrong base image!, base image can only be ubuntu:18.04 or ubuntu:20.04 at present." ;\
    fi

RUN wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add - \
    && apt-get update

# Install SGX-PSW
RUN apt-get install -y libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-quote-ex-dev libsgx-qe3-logic sgx-aesm-service

# Install SGX-DCAP
RUN apt-get install -y libsgx-dcap-ql-dev libsgx-dcap-default-qpl libsgx-dcap-quote-verify-dev libsgx-dcap-default-qpl-dev

# Gramine
ENV GRAMINEDIR=/gramine
ENV SGX_DCAP_VERSION=DCAP_1.11
# ENV GRAMINE_VERSION=b84f9de995422456fec02d48b0e02ef5938abc94
ENV GRAMINE_VERSION=v1.3.1
# ENV GRAMINE_VERSION=master
ENV ISGX_DRIVER_PATH=${GRAMINEDIR}/driver
# ENV SGX_SIGNER_KEY=${GRAMINEDIR}/Pal/src/host/Linux-SGX/signer/enclave-key.pem
ENV WERROR=1
ENV SGX=1

RUN apt-get update && apt-get install -y bison gawk nasm python3-click python3-jinja2 ninja-build pkg-config \
    libcurl4-openssl-dev libprotobuf-c-dev python3-protobuf protobuf-c-compiler \
    libgmp-dev libmpfr-dev libmpc-dev libisl-dev

RUN pip3 install --upgrade pip \
    && pip3 install 'meson>=0.56' 'toml>=0.10'

# for debug, just copy gramine from local in case failed to clone from github
#RUN mkdir -p ${GRAMINEDIR}
#COPY gramine_repo ${GRAMINEDIR}
#RUN cd ${GRAMINEDIR} && git checkout ${GRAMINE_VERSION}
RUN n=0; until [ $n -ge 100 ] ;  do echo $n; n=$(($n+1)); git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} && break; sleep 1; done \
    && cd ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

#for debug purpose, copy from local
#RUN mkdir -p ${ISGX_DRIVER_PATH}
#COPY SGXDataCenterAttestationPrimitives ${ISGX_DRIVER_PATH}
#RUN cd ${ISGX_DRIVER_PATH} && git checkout ${SGX_DCAP_VERSION}
RUN n=0; until [ $n -ge 100 ] ;  do echo $n; n=$(($n+1)); git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} && break; sleep 1; done \
    && cd ${ISGX_DRIVER_PATH} \
    && git checkout ${SGX_DCAP_VERSION}

#todo, debug purpose, need to remove later
#RUN cd ${GRAMINEDIR}/subprojects/packagefiles/mbedtls \
#    && sed -i -r "s/(.*)-O2(.*)/\1 -O0 -g -ggdb3 \2/" compile-gramine.sh \
#    && sed -i -r "s/(.*)-O2(.*)/\1 -O0 -g -ggdb3 \2/" compile-pal.sh

# COPY gramine/patches ${GRAMINEDIR}
# RUN cd ${GRAMINEDIR} \
#     && git apply *.diff

# Compile and install Gramine
# RUN openssl genrsa -3 -out ${SGX_SIGNER_KEY} 3072
RUN cd ${GRAMINEDIR} \
    && LD_LIBRARY_PATH="" meson setup build/ --buildtype=debug -Dprefix=${INSTALL_PREFIX} -Ddirect=enabled -Dsgx=enabled -Ddcap=enabled -Dsgx_driver=dcap1.10 -Dsgx_driver_include_path=${ISGX_DRIVER_PATH}/driver/linux/include \
    && LD_LIBRARY_PATH="" ninja -C build/ \
    && LD_LIBRARY_PATH="" ninja -C build/ install

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

RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/* \
    && rm -rf ${GRAMINEDIR}/build

RUN gramine-sgx-gen-private-key

COPY common/docker/gramine/configs /

#--------------------------------
# Install CLF
#--------------------------------
RUN apt-get update \
    && apt-get install -y openjdk-11-jdk openjdk-11-jdk-headless openjdk-11-jre openjdk-11-jre-headless

ARG CLF_DIR=/clf
ENV CLF_PATH=${CLF_DIR}
RUN n=0; until [ $n -ge 100 ] ;  do echo $n; n=$(($n+1)); git clone https://github.com/intel/confidential-computing-zoo.git ${CLF_PATH} && break; sleep 1; done
RUN cd ${CLF_PATH} \
    && git checkout branch-dev/cross_lang_framework \
    && echo "---build clf_client library---" \
    && cd ${CLF_PATH}/cczoo/cross_lang_framework/clf_client/java \
    && sed -i -r 's/(.*)(sudo )(.*)/\1\3/' Makefile \
    && GRAMINEDIR=/gramine make 

# Workspace
WORKDIR ${CLF_PATH}/cczoo/cross_lang_framework/clf_client/app

