#
# Copyright (c) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM occlum/occlum:0.27.3-ubuntu20.04

ARG http_proxy
ARG https_proxy
ENV DEBIAN_FRONTEND=noninteractive
ENV WORKSPACE=/lr_he_sgx
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:/usr/lib:/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8
ENV OCCLUM_VERSION=0.27.3
ENV OCCLUM_PATH=/occlum
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}

RUN apt-get update \
    && apt-get install -y --no-install-recommends apt-utils \
    && apt-get install -y ca-certificates build-essential \
        autoconf libtool python3-pip python3-dev git wget \
        unzip zip vim jq lsb-release golang strace gdb ctags \
        curl sshpass software-properties-common

# Install cmake
RUN wget http://cmake.org/files/v3.22/cmake-3.22.0.tar.gz \
    && tar xzvf cmake-3.22.0.tar.gz \
    && cd cmake-3.22.0 \
    && ./configure \
    && make install -j

WORKDIR $WORKSPACE

COPY src ./src/
COPY cmake ./cmake/
COPY datasets ./datasets/
COPY CMakeLists.txt ./

RUN cmake -S. -Bbuild \
    && cmake --build build
RUN occlum new occlum_instance \
    && cp build/src/infer_server occlum_instance/image/bin/ \
    && cd occlum_instance \
    && occlum build

# Clean apt cache
RUN apt-get clean all

ENV http_proxy=
ENV https_proxy=