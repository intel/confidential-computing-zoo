ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
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
        zlib1g-dev \
        numactl \
        wget \
        unzip \
        git \
        vim \
        jq

RUN wget https://download.01.org/intel-sgx/sgx-dcap/1.18/linux/distro/ubuntu22.04-server/sgx_debian_local_repo.tgz \
    && wget https://download.01.org/intel-sgx/sgx-dcap/1.18/linux/distro/ubuntu22.04-server/sgx_linux_x64_sdk_2.21.100.1.bin \
    && tar -zxvf sgx_debian_local_repo.tgz \
    && mkdir -p /opt/intel \
    && mv sgx_debian_local_repo sgx_linux_x64_sdk_*.bin /opt/intel/ \
    && echo "deb [trusted=yes arch=amd64] file:/opt/intel/sgx_debian_local_repo jammy main" > /etc/apt/sources.list.d/sgx_debian_local_repo.list \
    && rm -rf sgx_debian_local_repo.tgz

RUN apt-get update \
    && apt-get install -y \
        tdx-qgs \
        libsgx-enclave-common-dev \
        libsgx-dcap-default-qpl \
        sgx-ra-service \
    && apt-get install -y \
        libtdx-attest \
        libtdx-attest-dev \
    && apt-get install -y \
        libsgx-dcap-quote-verify \
        libsgx-dcap-quote-verify-dev \
        libsgx-ae-qve

COPY configs /
RUN chmod +x /opt/intel/sgx_linux_x64_sdk_2.21.100.1.bin \
    && /install_sgxsdk.sh /opt/intel/sgx_linux_x64_sdk_2.21.100.1.bin
ENV INTEL_SGXSDK_INCLUDE=/opt/intel/sgxsdk/include

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
ENV SGX_RA_TLS_BACKEND=TDX
ENV SGX_RA_TLS_SDK=DEFAULT
ENV BUILD_TYPE=Release

ARG GRPC_VERSION=v1.38.1
ARG GRPC_VERSION_PATH=${GRPC_ROOT}/${GRPC_VERSION}
RUN git clone --recurse-submodules -b ${GRPC_VERSION} https://github.com/grpc/grpc ${GRPC_VERSION_PATH}
RUN ln -s ${GRPC_VERSION_PATH} ${GRPC_PATH}
RUN pip3 install --upgrade pip \
    && pip3 install -r ${GRPC_PATH}/requirements.txt \
    && pip3 install cython==0.29.36
ARG CCZOO_VERSION=06499d3bda5ccde13f3c64c8e5ee6bd3eac6e5bd
RUN git clone https://github.com/intel/confidential-computing-zoo.git \
    && cd confidential-computing-zoo \
    && git checkout ${CCZOO_VERSION}
RUN cp -r confidential-computing-zoo/cczoo/grpc-ra-tls/grpc/common/* ${GRPC_PATH} \
    && cp -r confidential-computing-zoo/cczoo/grpc-ra-tls/grpc/${GRPC_VERSION}/* ${GRPC_PATH} \
    && sed -i "s/std::max(SIGSTKSZ, 65536)/std::max<size_t>(SIGSTKSZ, 65536)/g" ${GRPC_PATH}/third_party/abseil-cpp/absl/debugging/failure_signal_handler.cc

RUN cd ${GRPC_PATH} \
    && build_python.sh

RUN cd confidential-computing-zoo/utilities/tdx/tdx_report_parser \
    && make \
    && cp tdx_report.out /usr/bin/tdx_report_parser

RUN pip3 install optimum-intel urllib3==2.0.4

EXPOSE 8000
