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

ARG BASE_IMAGE=centos:8
FROM ${BASE_IMAGE}

ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}

RUN cd /etc/yum.repos.d/ && \
    sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-* && \
    sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-* && \
    yum makecache

# Add steps here to set up dependencies
RUN yum install -y yum-utils.noarch
RUN yum groupinstall -y 'Development Tools'

RUN yum install -y python3 python3-devel && \
    yum install -y python3-protobuf protobuf-c-devel protobuf-c-compiler openssl-devel libcurl-devel && \
    yum install -y cryptsetup e4fsprogs expect wget vim

RUN ln -s /usr/bin/python3 /usr/bin/python

ENV DCAP_VERSION=1.15
RUN wget https://download.01.org/intel-sgx/sgx-dcap/${DCAP_VERSION}/linux/distro/centos-stream/sgx_rpm_local_repo.tgz && \
    tar -xvf sgx_rpm_local_repo.tgz && \
    yum-config-manager --add-repo file://$(pwd)/sgx_rpm_local_repo/ && \
    yum install -y --setopt=install_weak_deps=False --nogpgcheck libtdx-attest && \
    yum install -y --setopt=install_weak_deps=False --nogpgcheck libtdx-attest-devel && \
    yum install -y --nogpgcheck sgx_rpm_local_repo/libsgx-dcap-default-qpl-*.el8.x86_64.rpm && \
    yum install -y --nogpgcheck sgx_rpm_local_repo/libsgx-dcap-quote-verify-*.el8.x86_64.rpm && \
    yum install -y --nogpgcheck sgx_rpm_local_repo/libsgx-urts-*.el8.x86_64.rpm && \
    yum install -y --setopt=install_weak_deps=False --nogpgcheck tdx-qgs && \
    yum install -y --setopt=install_weak_deps=False --nogpgcheck libsgx-dcap-quote-verify-devel && \
    yum install -y --setopt=install_weak_deps=False --nogpgcheck libsgx-ae-qve

# cmake tool chain
ARG CMAKE_VERSION=3.19.6
RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

ENV GRPC_ROOT=/grpc
ENV GRPC_PATH=${GRPC_ROOT}/src
ENV SGX_RA_TLS_BACKEND=TDX
ENV SGX_RA_TLS_SDK=DEFAULT
ENV BUILD_TYPE=Release

ARG GRPC_VERSION=v1.38.1
ARG GRPC_VERSION_PATH=${GRPC_ROOT}/${GRPC_VERSION}
RUN git clone --recurse-submodules -b ${GRPC_VERSION} https://github.com/grpc/grpc ${GRPC_VERSION_PATH} \
    && ln -s ${GRPC_VERSION_PATH} ${GRPC_PATH}
ARG CCZOO_VERSION=3a8a427ecb0849447b4dfd14292c3533d1fa5c1e
RUN git clone https://github.com/intel/confidential-computing-zoo.git /confidential-computing-zoo \
    && cd /confidential-computing-zoo \
    && git checkout ${CCZOO_VERSION} \
    && cd cczoo/grpc-ra-tls/grpc \
    && cp -r common/* ${GRPC_VERSION}/* ${GRPC_PATH} \
    && rm -rf /confidential-computing-zoo

RUN pip3 install --upgrade pip \
    && pip3 install -r ${GRPC_PATH}/requirements.txt

COPY examples ${GRPC_PATH}/examples/
COPY configs /

ENV WORK_SPACE_PATH=${GRPC_PATH}/examples/cpp/secretmanger
WORKDIR ${WORK_SPACE_PATH}

# build
RUN ./build.sh

# only for tdx vsock
# RUN echo 'port=4050' | tee /etc/tdx-attest.conf

# Clean tmp files
RUN yum clean all && \
    rm -rf ~/.cache/* && \
    rm -rf /tmp/*

EXPOSE 50051
ENTRYPOINT ["/bin/bash", "-c", "/root/entrypoint.sh"]
