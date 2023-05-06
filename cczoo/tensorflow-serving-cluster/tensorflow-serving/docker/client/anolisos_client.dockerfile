FROM openanolis/anolisos:8.4-x86_64

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Enable it to disable debconf warning
# RUN echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections

# Add steps here to set up dependencies
RUN yum update -y \
    && yum install -y --allowerasing \
        autoconf \
        bison \
        gcc \
        gcc-c++ \
        kernel-devel \ 
        make \
        coreutils \
        gawk \
        git \
        golang \
        libcurl-devel \
        mesa-libGL \
        protobuf-c-devel \
        protobuf-c-compiler \
        python3 \
        python3-protobuf \
        python3-pip \
        python3-devel \
        python3-click \
        python3-jinja2 \
        protobuf-c-devel \
        ninja-build \
        wget \
        curl \
    && yum install -y  yum-utils

RUN pip3 install --upgrade pip
RUN pip install django-model-utils

RUN mkdir client
COPY requirements.txt client/
RUN pip3 install -r client/requirements.txt
COPY resnet_client_grpc.py client/
COPY utils.py client/
