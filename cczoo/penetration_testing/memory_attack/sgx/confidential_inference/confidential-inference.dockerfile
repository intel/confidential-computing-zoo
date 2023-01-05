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

ENV DEBIAN_FRONTEND=noninteractive
ENV WERROR=1
ENV SGX=1

RUN apt-get update \
    && apt-get install -y libgl1-mesa-glx python3-pip python3-click python3-jinja2 python3-protobuf python3-dbg gdb tcpdump wget vim

RUN pip install --upgrade pip \
    && pip install toml meson cryptography pillow tensorflow opencv-python flask markupSafe==2.0.0

ARG ENV GRAMINE_VERSION=1.2
RUN wget https://github.com/gramineproject/gramine/releases/download/v${GRAMINE_VERSION}/gramine-dcap_${GRAMINE_VERSION}-1_amd64.deb \
    && apt-get install -y ./gramine-dcap_${GRAMINE_VERSION}-1_amd64.deb \
    && rm *.deb

RUN wget https://storage.googleapis.com/tensorflow/keras-applications/resnet/resnet50_weights_tf_dim_ordering_tf_kernels.h5

RUN gramine-sgx-gen-private-key

COPY demo /
