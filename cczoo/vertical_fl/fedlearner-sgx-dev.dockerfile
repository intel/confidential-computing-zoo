FROM ubuntu:20.04

# Optional build argument to select a build for Azure
ARG AZURE

ENV DEBIAN_FRONTEND=noninteractive
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8

# Add steps here to set up common dependencies
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
        lsb-release \
        unzip \
        wget \
        git \
        vim \
        jq

# Intel SGX PPA
RUN echo "deb [trusted=yes arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu $(lsb_release -sc) main" | tee /etc/apt/sources.list.d/intel-sgx.list \
    && wget -qO - https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add -

# Install SGX-PSW
RUN apt-get update \
    && apt-get install -y libsgx-pce-logic libsgx-ae-qve libsgx-quote-ex libsgx-quote-ex-dev libsgx-qe3-logic sgx-aesm-service

# Install SGX-DCAP
RUN apt-get update \
    && apt-get install -y libsgx-dcap-ql-dev libsgx-dcap-default-qpl libsgx-dcap-quote-verify-dev libsgx-dcap-default-qpl-dev

# Install SGX-DCAP quote provider library
RUN if [ -z "$AZURE" ]; then \
        # Not a build for Azure, so install the default quote provider library \
        apt-get install -y libsgx-dcap-default-qpl libsgx-dcap-default-qpl-dev; \
    else \
        # Build for Azure, so install the Azure DCAP Client (Release 1.10.0) \
        AZUREDIR=/azure \
        && apt-get install -y libssl-dev libcurl4-openssl-dev pkg-config software-properties-common \
        && add-apt-repository ppa:team-xbmc/ppa -y \
        && apt-get update \
        && apt-get install -y nlohmann-json3-dev \
        && git clone https://github.com/microsoft/Azure-DCAP-Client ${AZUREDIR} \
        && cd ${AZUREDIR} \
        && git checkout 1.10.0 \
        && git submodule update --recursive --init \
        && cd src/Linux \
        && ./configure \
        && make DEBUG=1 \
        && make install \
        && cp libdcap_quoteprov.so /usr/lib/x86_64-linux-gnu/; \
    fi

# Install CMAKE
ARG CMAKE_VERSION=3.19.6
RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

# Install BAZEL
ARG BAZEL_VERSION=3.1.0
RUN wget "https://github.com/bazelbuild/bazel/releases/download/${BAZEL_VERSION}/bazel_${BAZEL_VERSION}-linux-x86_64.deb" \
    && dpkg -i bazel_*.deb \
    && rm bazel_*.deb

# Gramine dependencies
## Golang is needed by grpc/BoringSSL
RUN apt-get update \
    && apt-get install -y bison gawk nasm ninja-build pkg-config golang python3-click python3-jinja2 python3-pyelftools \
    && apt-get install -y libcurl4-openssl-dev libprotobuf-c-dev python3-protobuf protobuf-c-compiler protobuf-compiler \
    && apt-get install -y libgmp-dev libmpfr-dev libmpc-dev libisl-dev \
    && apt-get install -y libunwind8 musl-tools python3-pytest \
    && apt-get install -y libmysqlclient-dev

# Gramine src
ENV GRAMINEDIR=/gramine
# ENV GRAMINE_VERSION=c662f63bba76736e6d5122a866da762efd1978c1
ENV GRAMINE_VERSION=v1.6
RUN git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && cd ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

ENV SGX_DRIVER_INC_PATH=${GRAMINEDIR}/driver_inc
RUN mkdir -p ${SGX_DRIVER_INC_PATH}/asm \
    && wget https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/plain/arch/x86/include/uapi/asm/sgx.h?h=v5.11 -O ${SGX_DRIVER_INC_PATH}/asm/sgx.h

# GRPC src
ENV GRPC_PATH=/grpc
ENV GRPC_VERSION=v1.38.1
# ENV GRPC_VERSION=b54a5b338637f92bfcf4b0bc05e0f57a5fd8fadd
RUN git clone --recurse-submodules -b ${GRPC_VERSION} https://github.com/grpc/grpc ${GRPC_PATH}

# Tensorflow src
ENV TF_PATH=/tf
ENV TF_SRC_PATH=${TF_PATH}/src
ENV TF_DIST_PATH=${TF_PATH}/dist
ENV TF_VERSION=v2.4.2
RUN git clone --recurse-submodules -b ${TF_VERSION} https://github.com/tensorflow/tensorflow ${TF_SRC_PATH}

# Fedlearner src
ENV FEDLEARNER_PATH=/fedlearner
ENV FEDLEARNER_VERSION=75e8043930c965cbe972bfc94c9582705fce9d0c
RUN git clone https://github.com/bytedance/fedlearner.git ${FEDLEARNER_PATH} \
    && cd ${FEDLEARNER_PATH} \
    && git checkout ${FEDLEARNER_VERSION}

RUN ln -s /usr/bin/python3 /usr/bin/python

# Python dependencies
RUN pip3 install pip --upgrade \
    && pip3 install -r ${GRPC_PATH}/requirements.txt \
    && pip3 install -r ${FEDLEARNER_PATH}/requirements.txt \
    && pip3 install 'cython==0.29.36' 'grpcio==1.38.1' 'grpcio_tools==1.38.1' 'numpy==1.19.2' 'keras_preprocessing==1.1.2' 'meson>=0.56' 'tomli>=1.1.0' 'tomli-w>=0.4.0' cryptography

# Build gramine
# https://gramine.readthedocs.io/en/latest/devel/building.html
ENV SGX=1
ENV WERROR=1
ENV BUILD_TYPE=release

COPY gramine/patches ${GRAMINEDIR}
RUN cd ${GRAMINEDIR} \
    && git apply *.diff

RUN cd ${GRAMINEDIR} \
    && LD_LIBRARY_PATH="" meson setup build/ --buildtype=${BUILD_TYPE} -Dprefix=${INSTALL_PREFIX} -Ddirect=enabled -Dsgx=enabled -Ddcap=enabled -Dlibgomp=enabled -Dsgx_driver_include_path=${SGX_DRIVER_INC_PATH} \
    && LD_LIBRARY_PATH="" ninja -C build/ \
    && LD_LIBRARY_PATH="" ninja -C build/ install

# Install mbedtls
RUN cd ${GRAMINEDIR}/build/subprojects/mbedtls-mbedtls* \
    && cp -r *_gramine.a ${INSTALL_PREFIX}/lib \
    && cp -r ${GRAMINEDIR}/build/subprojects/mbedtls-curl/include/* ${INSTALL_PREFIX}/include

# Install cJSON
RUN cd ${GRAMINEDIR}/subprojects/cJSON*/ \
    && make static \
    && cp -r *.a ${INSTALL_PREFIX}/lib \
    && mkdir -p ${INSTALL_PREFIX}/include/cjson \
    && cp -r *.h ${INSTALL_PREFIX}/include/cjson

# Build gRPC
COPY grpc/common ${GRPC_PATH}
COPY grpc/v1.38.1 ${GRPC_PATH}
RUN ${GRPC_PATH}/build_python.sh

# Build tensorflow
COPY tf ${TF_SRC_PATH}
RUN cd ${TF_SRC_PATH} \
    && git apply sgx_tls_sample.diff

ARG TF_BUILD_CFG="--config=numa --config=mkl --config=mkl_threadpool --copt=-march=native --copt=-O3 --cxxopt=-march=native --cxxopt=-O3 --cxxopt=-D_GLIBCXX_USE_CXX11_ABI=0"
RUN cd ${TF_SRC_PATH} \
    && bazel build -c opt ${TF_BUILD_CFG} //tensorflow/tools/pip_package:build_pip_package \
    && bazel-bin/tensorflow/tools/pip_package/build_pip_package ${TF_DIST_PATH}

# Build and install fedlearner
COPY fedlearner ${FEDLEARNER_PATH}
RUN cd ${FEDLEARNER_PATH} \
    && make protobuf \
    && python3 setup.py bdist_wheel

# Re-install fedlearner tensorflow and grpcio
RUN pip3 uninstall -y tensorflow tensorflow-io grpcio \
    && pip3 install ${FEDLEARNER_PATH}/dist/*.whl ${TF_DIST_PATH}/*.whl ${GRPC_PATH}/dist/grpcio*.whl 'tensorflow-io==0.17.1' 'markupsafe==2.0.1'

# Re-install fedlearner plugin
RUN cd ${FEDLEARNER_PATH} \
    && make op \
    && mkdir -p /usr/local/lib/python3.8/dist-packages/cc \
    && cp ./cc/embedding.so /usr/local/lib/python3.8/dist-packages/cc

# For debug
RUN apt-get install -y strace gdb ctags

# RA-TLS ENV
ENV FL_GRPC_SGX_RA_TLS_ENABLE=on
ENV TF_GRPC_SGX_RA_TLS_ENABLE=on
ENV RA_TLS_CERT_SIGNATURE_ALGO=RSA
ENV RA_TLS_ALLOW_HW_CONFIG_NEEDED=1
ENV RA_TLS_ALLOW_SW_HARDENING_NEEDED=1
# ENV RA_TLS_ALLOW_OUTDATED_TCB_INSECURE=1
# ENV RA_TLS_ALLOW_DEBUG_ENCLAVE_INSECURE=1

COPY gramine/CI-Examples ${GRAMINEDIR}/CI-Examples
COPY configs /

RUN gramine-sgx-gen-private-key

# https://askubuntu.com/questions/93457/how-do-i-enable-or-disable-apport
RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

# Clean tmp files
RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*

# Workspace
ENV WORK_SPACE_PATH=${GRAMINEDIR}/CI-Examples
WORKDIR ${WORK_SPACE_PATH}

EXPOSE 6006 50051 50052

RUN chmod +x /root/entrypoint.sh
# ENTRYPOINT ["/root/entrypoint.sh"]
