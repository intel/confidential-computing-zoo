FROM openanolis/anolisos:8.4-x86_64

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Enable it to disable debconf warning
# RUN echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections

# Add steps here to set up dependencies
RUN yum update -y && \
    yum install -y yum-utils epel-release && \
    yum install -y --allowerasing \
        autoconf \
        bison \
        gcc \
        gcc-c++ \
        make \
        ninja-build \
        kernel-devel \
        coreutils \
        python38 \
        python38-devel \
        protobuf-c-devel \
        protobuf-c-compiler \
        libcurl-devel \
        mesa-libGL \
        gawk \
        git \
        wget \
        curl

RUN mkdir client

COPY requirements.txt client/
RUN pip3 install --upgrade pip && \
    pip3 install click jinja2 protobuf django-model-utils && \
    pip3 install -r client/requirements.txt

COPY resnet_client_grpc.py client/
COPY utils.py client/
