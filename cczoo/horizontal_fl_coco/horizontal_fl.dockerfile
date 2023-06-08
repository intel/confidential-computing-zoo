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
RUN yum install -y python3 python3-devel
RUN yum install -y python3-protobuf protobuf-c-devel protobuf-c-compiler openssl-devel libcurl-devel
RUN yum install -y cryptsetup e4fsprogs expect wget vim

# only install for non-tdx testing
# RUN yum install -y ca-certificates

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

# config and download TensorFlow
ENV TF_VERSION=v2.6.0
ENV TF_BUILD_PATH=/tf/src
ENV TF_BUILD_OUTPUT=/tf/output
RUN git clone --recurse-submodules -b ${TF_VERSION} https://github.com/tensorflow/tensorflow ${TF_BUILD_PATH}

# git apply diff
COPY tf_v2.6.diff ${TF_BUILD_PATH}
COPY grpc_ratls.patch ${TF_BUILD_PATH}/third_party/grpc/
RUN cd ${TF_BUILD_PATH} && git apply tf_v2.6.diff

# bazel
RUN curl -fSsL -O https://github.com/bazelbuild/bazel/releases/download/3.7.2/bazel-3.7.2-installer-linux-x86_64.sh && \
    sh bazel-3.7.2-installer-linux-x86_64.sh

# deps
RUN pip3 install --upgrade pip && \
    pip3 install toml meson numpy keras==2.6 keras_preprocessing pandas sklearn matplotlib wheel

# build and install TensorFlow
ENV SGX_RA_TLS_BACKEND=TDX
RUN cd ${TF_BUILD_PATH} && \
    bazel build -c opt //tensorflow/tools/pip_package:build_pip_package && \
    bazel-bin/tensorflow/tools/pip_package/build_pip_package ${TF_BUILD_OUTPUT} && \
    rm -rf ~/.cache/bazel
RUN pip3 install ${TF_BUILD_OUTPUT}/tensorflow-*-cp36-cp36m-linux_x86_64.whl keras==2.6 --upgrade

# download and exact cifar-10 dataset
ENV WORKDIR=/hfl-tensorflow
WORKDIR ${WORKDIR}
RUN wget https://www.cs.toronto.edu/~kriz/cifar-10-binary.tar.gz && tar -xvzf cifar-10-binary.tar.gz

COPY hfl-tensorflow /hfl-tensorflow
COPY sgx_default_qcnl.conf /etc/sgx_default_qcnl.conf
COPY luks_tools /luks_tools

# only for tdx vsock
RUN echo 'port=4050' | tee /etc/tdx-attest.conf

# Clean tmp files
RUN yum clean all && \
    rm -rf ~/.cache/* && \
    rm -rf /tmp/*

ENV TF_GRPC_SGX_RA_TLS_ENABLE="on"

RUN chmod +x entrypoint.sh
ENTRYPOINT ["/bin/bash", "-c", "/hfl-tensorflow/entrypoint.sh ps0"]
# ENTRYPOINT ["/bin/bash", "-c", "sleep infinity"]
