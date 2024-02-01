ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8

# Install initial dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends apt-utils \
    && apt-get install -y \
        ca-certificates \
        build-essential \
        autoconf \
        libtool \
        python3-pip \
        python3-dev \
        zlib1g-dev \
        numactl \
        wget \
        unzip \
        git \
        vim \
        jq \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /dcap
RUN wget https://download.01.org/intel-sgx/sgx-dcap/1.19/linux/distro/ubuntu20.04-server/sgx_debian_local_repo.tgz \
    && tar -xvf sgx_debian_local_repo.tgz \
    && rm -rf sgx_debian_local_repo.tgz
RUN ["/bin/bash", "-c", "set -o pipefail && echo 'deb [trusted=yes arch=amd64] file:/dcap/sgx_debian_local_repo focal main' | tee /etc/apt/sources.list.d/intel-sgx.list"]

RUN apt-get update && apt-get install -y --no-install-recommends \
# required for gRPC build
        libcurl4-openssl-dev nlohmann-json3-dev \
# SGX PSW packages required for gRPC build
        libtdx-attest \
        libtdx-attest-dev \
# required for attestation client
        libjsoncpp-dev libboost-all-dev tpm2-tools \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Azure confidential-computing-cvm-guest-attestation
WORKDIR /
RUN git clone -b tdx-preview https://github.com/Azure/confidential-computing-cvm-guest-attestation
WORKDIR /confidential-computing-cvm-guest-attestation
RUN git checkout e045e8f52543f823f9a85d1b33338f99dec70397
WORKDIR /confidential-computing-cvm-guest-attestation/tdx-attestation-app
RUN wget http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_amd64.deb \
    && dpkg -i libssl1.1_1.1.1f-1ubuntu2_amd64.deb \
    && rm libssl1.1_1.1.1f-1ubuntu2_amd64.deb
RUN dpkg -i package/azguestattestation1_1.0.3_amd64.deb

# cmake tool chain
ARG CMAKE_VERSION=3.19.6
RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

WORKDIR /home/user
RUN git config --global user.email "llm@intel.com"
RUN git config --global user.name "intel"
ARG COMMIT_ID
RUN git clone https://github.com/deepset-ai/haystack.git

WORKDIR /home/user/haystack
COPY patches /home/user/haystack/patches
RUN git checkout $COMMIT_ID
RUN git am patches/*

# Install package
RUN pip install --upgrade pip
# RUN pip install --no-cache-dir .[docstores,crawler,preprocessing,ocr,ray]
RUN pip install .[all]
RUN pip install rest_api/
RUN pip install torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu
RUN pip install intel-extension-for-pytorch
RUN pip install numba sacremoses einops tokenizers==0.13.3 grpcio==1.38.1 grpcio-tools==1.38.1

COPY hot-fix/text_generation.py /usr/local/lib/python3.10/dist-packages/transformers/pipelines/text_generation.py

WORKDIR /home/user

ENV GRPC_ROOT=/grpc
ENV GRPC_PATH=${GRPC_ROOT}/src
ENV SGX_RA_TLS_BACKEND=AZURE_TDX
ENV SGX_RA_TLS_SDK=DEFAULT
ENV BUILD_TYPE=Release

ARG GRPC_VERSION=v1.38.1
ARG GRPC_VERSION_PATH=${GRPC_ROOT}/${GRPC_VERSION}
RUN git clone --recurse-submodules -b ${GRPC_VERSION} https://github.com/grpc/grpc ${GRPC_VERSION_PATH}
RUN ln -s ${GRPC_VERSION_PATH} ${GRPC_PATH}
RUN pip3 install --upgrade pip \
    && pip3 install -r ${GRPC_PATH}/requirements.txt \
    && pip3 install cython==0.29.36
ARG CCZOO_VERSION=5a527c827a43a2d99c217ecb9e35204df1c31652
RUN git clone https://github.com/intel/confidential-computing-zoo.git \
    && cd confidential-computing-zoo \
    && git checkout ${CCZOO_VERSION}
RUN cp -r confidential-computing-zoo/cczoo/grpc-ra-tls/grpc/common/* ${GRPC_PATH} \
    && cp -r confidential-computing-zoo/cczoo/grpc-ra-tls/grpc/${GRPC_VERSION}/* ${GRPC_PATH}
RUN sed -i "s/std::max(SIGSTKSZ, 65536)/std::max<size_t>(SIGSTKSZ, 65536)/g" ${GRPC_PATH}/third_party/abseil-cpp/absl/debugging/failure_signal_handler.cc

RUN cd ${GRPC_PATH} \
    && build_python.sh

#RUN cd confidential-computing-zoo/utilities/tdx/tdx_report_parser \
#    && make \
#    && cp tdx_report.out /usr/bin/tdx_report_parser

RUN apt update && apt install -y default-libmysqlclient-dev pkg-config && pip3 install optimum-intel urllib3==2.0.4 mysqlclient==2.2.0

COPY attest_config/attest_config.json /etc

WORKDIR /home/user
COPY requirements.txt /home/user
RUN pip3 install -r requirements.txt

EXPOSE 8000
