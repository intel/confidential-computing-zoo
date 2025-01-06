FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8

WORKDIR /home/user

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y \
        ca-certificates \
        python3  \
        python3-pip \
        libpoppler-cpp-dev \
        wget \
        git \
        poppler-utils \
        libmkl-dev \
        vim

COPY configs/config.toml /root/.streamlit/

# Install package
# RUN ln -s /usr/bin/python3.8 /usr/bin/python
RUN pip install --upgrade pip
RUN pip install --no-cache-dir streamlit streamlit-chat matplotlib pyyaml grpcio==1.38.1 grpcio-tools==1.38.1

ARG DCAP_VERSION
RUN wget https://download.01.org/intel-sgx/sgx-dcap/${DCAP_VERSION}/linux/distro/ubuntu22.04-server/sgx_debian_local_repo.tgz \
    && wget -qO- https://download.01.org/intel-sgx/sgx-dcap/${DCAP_VERSION}/linux/distro/ubuntu22.04-server/ | \
    grep -oP 'sgx_linux_x64_sdk_\d+(\.\d+)*\.bin' | head -n 1 | \
    xargs -I {} wget https://download.01.org/intel-sgx/sgx-dcap/${DCAP_VERSION}/linux/distro/ubuntu22.04-server/{} \
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

COPY ra_configs /
RUN chmod +x /opt/intel/sgx_linux_x64_sdk_*.bin \
    && /install_sgxsdk.sh /opt/intel/sgx_linux_x64_sdk_*.bin
ENV INTEL_SGXSDK_INCLUDE=/opt/intel/sgxsdk/include

# cmake tool chain
ARG CMAKE_VERSION=3.19.6
RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

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
ARG CCZOO_VERSION=051bbc9f4d6a0c9476341f33161e5775536f62b4
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

EXPOSE 8502
