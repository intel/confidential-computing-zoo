# Copyright (c) 2023 Intel
#
# SPDX-License-Identifier: Apache-2.0

FROM runetest/compilation-testing:ubuntu20.04 AS builder
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        clang \
        cmake \
        curl \
        gcc \
        golang-go \
        make \
        git \
        libcurl4-openssl-dev \
        libprotobuf-dev \
        llvm \
        llvm-dev \
        libclang-dev \
        protobuf-compiler && \
    apt-get clean && rm -rf /var/lib/lists/ && \
    curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain 1.62.0 && \
    source "$HOME/.cargo/env" && \
    rustup component add rust-src

# Prepare build dependency for tdx support
RUN \
    curl -L https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add - &&\
    echo 'deb [arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main' | tee /etc/apt/sources.list.d/intel-sgx.list &&\
    apt-get update && apt-get install -y libtdx-attest libtdx-attest-dev &&\
    curl -L -o opa https://openpolicyagent.org/downloads/v0.30.1/opa_linux_amd64_static && \
    chmod 755 ./opa && \
    mv opa /usr/local/bin/opa

# Clone verdictd and rats-tls
RUN \
    git clone --depth=1 https://github.com/inclavare-containers/verdictd.git && \
    cd verdictd && \
    git clone https://github.com/inclavare-containers/rats-tls &&\
    cd rats-tls &&\
    git reset --hard 5de6fc308f2a18f4105429451c85e6173b42ab9d

# Build and install verdictd
Run \
    cd verdictd/rats-tls &&\
    cmake -DRATS_TLS_BUILD_MODE="tdx" -DBUILD_SAMPLES=on -H. -Bbuild &&\
    make -C build install &&\
    cd .. &&\
    make && make install

FROM ubuntu:20.04
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        openssl

COPY --from=builder /usr/local/lib/libopa.so /usr/local/lib/
COPY --from=builder /usr/local/lib/rats-tls/ /usr/local/lib/rats-tls/
COPY --from=builder /usr/local/bin/verdictd /usr/local/bin
COPY --from=builder /usr/share/rats-tls/samples/ /usr/share/rats-tls/samples/
RUN \
    curl -L https://download.01.org/intel-sgx/sgx_repo/ubuntu/intel-sgx-deb.key | apt-key add - &&\
    echo 'deb [arch=amd64] https://download.01.org/intel-sgx/sgx_repo/ubuntu focal main' | tee /etc/apt/sources.list.d/intel-sgx.list &&\
    apt-get update && \
    apt-get install -y --no-install-recommends libtdx-attest libsgx-dcap-quote-verify && \
    apt-get clean && rm -rf /var/lib/lists/

CMD ["--client-api", "127.0.0.1:50001", "--listen", "0.0.0.0:50000"]
ENTRYPOINT ["/usr/local/bin/verdictd"]
