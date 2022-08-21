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
FROM openanolis/anolisos:8.4-x86_64 AS Anolisos

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib64:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
# Add steps here to set up dependencies
RUN yum clean all && yum update -y \
    && yum install -y \
        openssl-devel \
        libcurl-devel \
        protobuf-devel \
        yum-utils.noarch \
        python3 \
        wget

# Intel SGX
RUN mkdir /opt/intel && cd /opt/intel \
    && wget https://mirrors.openanolis.cn/inclavare-containers/bin/anolis8.4/sgx-2.15.1/sgx_rpm_local_repo.tar.gz 
RUN cd /opt/intel && sha256sum sgx_rpm_local_repo.tar.gz \
    && tar xvf sgx_rpm_local_repo.tar.gz \
    && yum-config-manager --add-repo file:///opt/intel/sgx_rpm_local_repo \
    && yum --nogpgcheck install -y libsgx-urts libsgx-launch libsgx-epid libsgx-quote-ex libsgx-dcap-ql libsgx-uae-service libsgx-dcap-quote-verify-devel 
RUN yum groupinstall -y 'Development Tools'

# Gramine
ENV GRAMINEDIR=/gramine
ENV SGX_DCAP_VERSION=DCAP_1.11
ENV GRAMINE_VERSION=v1.2
ENV ISGX_DRIVER_PATH=${GRAMINEDIR}/driver
ENV PKG_CONFIG_PATH=/usr/lib64/pkgconfig/
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8
ENV WERROR=1
ENV SGX=1
ENV GRAMINE_PKGLIBDIR=/usr/lib64/gramine
ENV ARCH_LIBDIR=/lib64

RUN yum install -y gawk bison python3-click python3-jinja2 golang ninja-build 
RUN yum install -y openssl-devel protobuf-c-devel python3-protobuf protobuf-c-compiler
RUN yum install -y gmp-devel mpfr-devel libmpc-devel isl-devel nasm python3-devel mailcap

RUN ln -s /usr/bin/python3 /usr/bin/python \
    && pip3 install --upgrade pip \
    && pip3 install toml meson wheel

RUN rm -rf ${GRAMINEDIR} && git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && cd ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && cd ${ISGX_DRIVER_PATH} \
    && git checkout ${SGX_DCAP_VERSION}

RUN cd ${GRAMINEDIR} \
    && LD_LIBRARY_PATH="" meson setup build/ --buildtype=debug -Dprefix=${INSTALL_PREFIX} -Ddirect=enabled -Dsgx=enabled -Ddcap=enabled -Dsgx_driver=dcap1.10 -Dsgx_driver_include_path=${ISGX_DRIVER_PATH}/driver/linux/include \
    && LD_LIBRARY_PATH="" ninja -C build/ \
    && LD_LIBRARY_PATH="" ninja -C build/ install

FROM Anolisos AS Hfl_tensorflow
# Install mbedtls
RUN cd ${GRAMINEDIR}/build/subprojects/mbedtls-mbedtls* \
    && cp -i `find . -name "*_gramine.a"` ${INSTALL_PREFIX}/lib \
    && cp -r ${GRAMINEDIR}/subprojects/mbedtls-mbedtls*/include ${INSTALL_PREFIX}

# Install cJSON
RUN ls ${GRAMINEDIR}/subprojects
RUN cd ${GRAMINEDIR}/subprojects/cJSON*/ \
    && make static \
    && cp -r *.a ${INSTALL_PREFIX}/lib \
    && mkdir -p ${INSTALL_PREFIX}/include/cjson \
    && cp -r *.h ${INSTALL_PREFIX}/include/cjson

# bazel
RUN cd /usr/bin && curl -fLO https://releases.bazel.build/3.1.0/release/bazel-3.1.0-linux-x86_64 && chmod +x bazel-3.1.0-linux-x86_64 

# deps 
RUN python3 -m pip install numpy keras_preprocessing cryptography pyelftools && pip3 install --upgrade pip setuptools==44.1.1

# config and download TensorFlow
ENV TF_VERSION=v2.4.2
ENV TF_BUILD_PATH=/tf/src
ENV TF_BUILD_OUTPUT=/tf/output
RUN rm -rf ${TF_BUILD_PATH} && git clone  --recurse-submodules -b ${TF_VERSION} https://github.com/tensorflow/tensorflow ${TF_BUILD_PATH}

# git apply diff
COPY patches/tf ${TF_BUILD_PATH}
COPY patches/gramine ${GRAMINEDIR} 
RUN cd ${TF_BUILD_PATH} && git apply tf2_4.diff

# build and install TensorFlow
RUN gramine-sgx-gen-private-key
RUN cd ${TF_BUILD_PATH} && ./build.sh anolisos
RUN cd ${TF_BUILD_PATH} && bazel-3.1.0-linux-x86_64 build -c opt //tensorflow/tools/pip_package:build_pip_package
RUN cd ${TF_BUILD_PATH} && bazel-bin/tensorflow/tools/pip_package/build_pip_package ${TF_BUILD_OUTPUT} && pip install ${TF_BUILD_OUTPUT}/tensorflow-*-cp36-cp36m-linux_x86_64.whl

# aesm service
COPY patches/sgx_default_qcnl.conf /etc
COPY patches/start_aesm_service.sh /

#download and exact cifar-10 dataset
RUN mkdir /hfl-tensorflow
COPY hfl-tensorflow /hfl-tensorflow
COPY patches/hfl-tensorflow /hfl-tensorflow
RUN cd /hfl-tensorflow && cat manifest.diff && git apply manifest.diff && wget https://www.cs.toronto.edu/~kriz/cifar-10-binary.tar.gz && tar -xvzf cifar-10-binary.tar.gz

# disable apport
RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

#make project
RUN cd /hfl-tensorflow && test-sgx.sh make


RUN yum clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/pip/* \
    && rm -rf /tmp/* 
    

EXPOSE 6006 50051 50052