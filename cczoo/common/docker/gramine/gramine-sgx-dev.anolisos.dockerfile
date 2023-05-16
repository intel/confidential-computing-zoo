
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
FROM openanolis/anolisos:8.4-x86_64 AS Anolisos

ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib64:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
# Add steps here to set up dependencies
RUN yum -y install \
    openssl-devel \
    libcurl-devel \
    protobuf-devel \
    yum-utils.noarch \
    python3 \
    wget

# Intel SGX
RUN mkdir /opt/intel && cd /opt/intel \
    && wget https://mirrors.openanolis.cn/inclavare-containers/bin/anolis8.4/sgx-2.15.1/sgx_rpm_local_repo.tar.gz \
    && sha256sum sgx_rpm_local_repo.tar.gz \
    && tar xvf sgx_rpm_local_repo.tar.gz \
    && yum-config-manager --add-repo file:///opt/intel/sgx_rpm_local_repo \
    && yum -y --nogpgcheck install libsgx-urts libsgx-launch libsgx-epid libsgx-quote-ex libsgx-dcap-ql libsgx-uae-service libsgx-dcap-quote-verify-devel \
    && yum -y groupinstall 'Development Tools'

# COPY patches/libsgx_dcap_quoteverify.so  /usr/lib64/
RUN yum -y install --nogpgcheck sgx-dcap-pccs libsgx-dcap-default-qpl

# Gramine
ENV GRAMINEDIR=/gramine
ENV SGX_DCAP_VERSION=DCAP_1.11
ENV GRAMINE_VERSION=v1.2
ENV ISGX_DRIVER_PATH=${GRAMINEDIR}/driver
ENV PKG_CONFIG_PATH=/usr/local/lib64/pkgconfig/
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8
ENV WERROR=1
ENV SGX=1
ENV GRAMINE_PKGLIBDIR=/usr/local/lib64/gramine
ENV ARCH_LIBDIR=/lib64

RUN yum -y install gawk bison python3-click python3-jinja2 golang ninja-build 
RUN yum -y install openssl-devel protobuf-c-devel python3-protobuf protobuf-c-compiler
RUN yum -y install gmp-devel mpfr-devel libmpc-devel isl-devel nasm python3-devel mailcap
#install gramine
RUN ln -s /usr/bin/python3 /usr/bin/python \
    && python3 -m pip install --upgrade pip \
    && python3 -m pip install toml meson wheel cryptography paramiko \
    && git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && cd ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && cd ${ISGX_DRIVER_PATH} \
    && git checkout ${SGX_DCAP_VERSION}

ARG BUILD_TYPE=release
RUN cd ${GRAMINEDIR} \
    && LD_LIBRARY_PATH="" meson setup build/ --buildtype=${BUILD_TYPE} -Dprefix=${INSTALL_PREFIX} -Ddirect=enabled -Dsgx=enabled -Ddcap=enabled -Dsgx_driver=dcap1.10 -Dsgx_driver_include_path=${ISGX_DRIVER_PATH}/driver/linux/include \
    && LD_LIBRARY_PATH="" ninja -C build/ \
    && LD_LIBRARY_PATH="" ninja -C build/ install
RUN gramine-sgx-gen-private-key

FROM Anolisos AS Psi_tensorflow
# Install mbedtls
RUN cd ${GRAMINEDIR}/build/subprojects/mbedtls-mbedtls* \
    && cp -r *_gramine.a ${INSTALL_PREFIX}/lib \
    && cd ${GRAMINEDIR}/subprojects/mbedtls-mbedtls*/mbedtls-mbedtls* \
    && cp -r include/mbedtls ${INSTALL_PREFIX}/include

# Install cJSON
RUN cd ${GRAMINEDIR}/subprojects/cJSON*/ \
    && make static \
    && cp -r *.a ${INSTALL_PREFIX}/lib \
    && mkdir -p ${INSTALL_PREFIX}/include/cjson \
    && cp -r *.h ${INSTALL_PREFIX}/include/cjson

RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

# Clean tmp files
RUN yum -y clean all && rm -rf /var/cache

COPY configs /

# Workspace
ENV WORK_SPACE_PATH=${GRAMINEDIR}
WORKDIR ${WORK_SPACE_PATH}