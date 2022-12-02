FROM openanolis/anolisos:8.4-x86_64 AS Anolisos

ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib64:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
# Add steps here to set up dependencies
RUN yum install -y \
    openssl-devel \
    libcurl-devel \
    protobuf-devel \
    yum-utils.noarch \
    python3 \
    wget

# Intel SGX
RUN mkdir /opt/intel && cd /opt/intel \
    && wget https://mirrors.openanolis.cn/inclavare-containers/bin/anolis8.4/sgx-2.15.1/sgx_rpm_local_repo.tar.gz 
RUN cd /opt/intel && sha256sum sgx_rpm_local_repo.tar.gz \
    && tar xvf sgx_rpm_local_repo.tar.gz \
    && yum-config-manager --add-repo file:///opt/intel/sgx_rpm_local_repo \
    && yum --nogpgcheck install -y libsgx-urts libsgx-launch libsgx-epid libsgx-quote-ex libsgx-dcap-ql libsgx-uae-service libsgx-dcap-quote-verify-devel 
RUN yum groupinstall -y 'Development Tools'

# COPY patches/libsgx_dcap_quoteverify.so  /usr/lib64/
RUN yum install -y --nogpgcheck sgx-dcap-pccs libsgx-dcap-default-qpl

# Gramine
ENV GRAMINEDIR=/gramine
ENV SGX_DCAP_VERSION=DCAP_1.11
ENV GRAMINE_VERSION=v1.3.1
ENV ISGX_DRIVER_PATH=${GRAMINEDIR}/driver
ENV PKG_CONFIG_PATH=/usr/local/lib64/pkgconfig/
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8
ENV WERROR=1
ENV SGX=1
ENV GRAMINE_PKGLIBDIR=/usr/local/lib64/gramine
ENV ARCH_LIBDIR=/lib64

RUN yum install -y gawk bison python3-click python3-jinja2 golang ninja-build 
RUN yum install -y openssl-devel protobuf-c-devel python3-protobuf protobuf-c-compiler protobuf-compiler
RUN yum install -y gmp-devel mpfr-devel libmpc-devel isl-devel nasm python3-devel mailcap

RUN ln -s /usr/bin/python3 /usr/bin/python \
    && pip3 install --upgrade pip \
    && pip3 install toml meson wheel cryptography paramiko pyelftools

RUN git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
    && cd ${GRAMINEDIR} \
    && git checkout ${GRAMINE_VERSION}

RUN git clone https://github.com/intel/SGXDataCenterAttestationPrimitives.git ${ISGX_DRIVER_PATH} \
    && cd ${ISGX_DRIVER_PATH} \
    && git checkout ${SGX_DCAP_VERSION}

ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib64:${LD_LIBRARY_PATH}
RUN cd ${GRAMINEDIR} \
    && LD_LIBRARY_PATH="" meson setup build/ --buildtype=debug -Dprefix=${INSTALL_PREFIX} -Ddirect=enabled -Dsgx=enabled -Ddcap=enabled -Dsgx_driver=dcap1.10 -Dsgx_driver_include_path=${ISGX_DRIVER_PATH}/driver/linux/include \
    && LD_LIBRARY_PATH="" ninja -C build/ \
    && LD_LIBRARY_PATH="" ninja -C build/ install
RUN gramine-sgx-gen-private-key

RUN echo "enabled=0" > /etc/default/apport
RUN echo "exit 0" > /usr/sbin/policy-rc.d

RUN mkdir -p ${INSTALL_PREFIX} \
    && wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v3.19.6/cmake-3.19.6-Linux-x86_64.sh \
    && sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX} \
    && rm cmake-linux.sh

# Clean tmp files
RUN yum -y clean all \
    && rm -rf /var/cache \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*

ENV WORKSPACE=/lr_infer_he_sgx
WORKDIR ${WORKSPACE}

COPY src ./src
COPY datasets ./datasets
COPY cmake ./cmake
COPY CMakeLists.txt \
     start_service.sh \
     infer_server.manifest.template \
     Makefile ./

RUN cmake -S. -Bbuild \
    && cmake --build build \
    && cp build/src/infer_server . \
    && cp datasets/lrtest_mid_lrmodel.csv . \
    && make clean \
    && ENTRYPOINT=infer_server make

RUN echo "/lr_infer_he_sgx/start_service.sh" >> ~/.bashrc