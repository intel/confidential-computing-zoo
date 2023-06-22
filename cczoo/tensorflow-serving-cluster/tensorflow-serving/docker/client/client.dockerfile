FROM ubuntu:20.04

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Enable it to disable debconf warning
RUN ["/bin/bash", "-c", "set -o pipefail && echo 'debconf debconf/frontend select Noninteractive' | debconf-set-selections"]

# Add steps here to set up dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
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
        python3 \
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
        libglib2.0-0 \
        apt-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --upgrade \
    'pip>=23.1.2' \
    'django-model-utils>=4.3.1' \
    'wheel>=0.38.0'

WORKDIR /client
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY resnet_client_grpc.py . 
COPY utils.py .
COPY run_inference.sh .
