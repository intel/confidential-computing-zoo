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

ENV DCAP_VERSION=TDX/MVP/2023ww15
RUN tar -zxvf dcap-20230406.tar.gz \
    && cd dcap-20230406/Ubuntu22.04 \
    && tar -zxvf sgx_debian_local_repo.tar.gz \
    && mkdir -p /opt/intel \
    && mv sgx_debian_local_repo sgx_linux_x64_sdk_*.bin libsgx_dcap_quoteverify.so /opt/intel/ \
    && echo "deb [trusted=yes arch=amd64] file:/opt/intel/sgx_debian_local_repo jammy main" > /etc/apt/sources.list.d/sgx_debian_local_repo.list \
    && cd - \
    && rm -rf dcap-20230406.tar.gz dcap-20230406

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
        libsgx-ae-qve \
    && mv -f /opt/intel/libsgx_dcap_quoteverify.so /usr/lib/x86_64-linux-gnu/libsgx_dcap_quoteverify.so.1.12.103.3

RUN cd /opt/intel \
    && git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git \
    && cd SGXDataCenterAttestationPrimitives \
    && git checkout 6f77ba8f153e7cecd8da3cf65a0f1bb0cdc1f638

COPY ra_configs /
RUN chmod +x /opt/intel/sgx_linux_x64_sdk_2.19.90.3.bin \
    && /install_sgxsdk.sh /opt/intel/sgx_linux_x64_sdk_2.19.90.3.bin
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

EXPOSE 8502
