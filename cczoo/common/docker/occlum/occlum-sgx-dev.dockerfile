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

ARG base_image=occlum/occlum:0.26.3-ubuntu18.04
FROM ${base_image}

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:/usr/lib:/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
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
        wget \
        unzip \
        vim \
        jq

ENV OCCLUM_VERSION=0.26.3
ENV OCCLUM_PATH=/occlum

RUN git clone -b ${OCCLUM_VERSION} https://github.com/occlum/occlum ${OCCLUM_PATH}

RUN cd ${OCCLUM_PATH} \
    && make submodule \
    && cd ${OCCLUM_PATH}/demos/remote_attestation/dcap/dcap_lib \
    && cargo build --all-targets \
    && cp target/debug/libdcap_quote.a ${INSTALL_PREFIX}/lib/ \
    && cp ../c_app/dcap_quote.h ${INSTALL_PREFIX}/include/

COPY configs /

RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*
