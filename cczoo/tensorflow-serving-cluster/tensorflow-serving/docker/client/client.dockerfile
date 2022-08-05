FROM ubuntu:20.04

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Enable it to disable debconf warning
RUN echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections

# Add steps here to set up dependencies
RUN apt-get update \
    && apt-get install -y \
        autoconf \
        bison \
        build-essential \
        coreutils \
        gawk \
        git \
        golang \
        libcurl4-openssl-dev \
        libgl1-mesa-glx \
        libprotobuf-c-dev \
        protobuf-c-compiler \
        python3.7 \
        python3-protobuf \
        python3-pip \
        python3-dev \
        python3-click \
        python3-jinja2 \
        libnss-mdns \
        libnss-myhostname \
        libcurl4-openssl-dev \
        libprotobuf-c-dev \
        ninja-build \
        wget \
        curl \
    && apt-get install -y --no-install-recommends apt-utils

RUN pip3 install --upgrade pip
RUN pip install django-model-utils

RUN mkdir client
RUN mkdir -p client/ssl_configure
COPY requirements.txt client/
RUN pip3 install -r client/requirements.txt
COPY resnet_client_grpc.py client/
COPY utils.py client/
COPY ssl_configure client/ssl_configure

