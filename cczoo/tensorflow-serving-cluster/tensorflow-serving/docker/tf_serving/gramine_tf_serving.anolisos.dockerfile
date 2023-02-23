FROM openanolis/anolisos:8.4-x86_64 AS Anolisos

ENV GRAMINEDIR=/gramine
ENV WORK_BASE_PATH=${GRAMINEDIR}/CI-Examples/tensorflow-serving-cluster/tensorflow-serving
ENV INSTALL_PREFIX=/usr/local
ENV LD_LIBRARY_PATH=${INSTALL_PREFIX}/lib:${INSTALL_PREFIX}/lib64:${LD_LIBRARY_PATH}
ENV PATH=${INSTALL_PREFIX}/bin:${LD_LIBRARY_PATH}:${PATH}
# Add steps here to set up dependencies
RUN yum -y install \
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
    && yum --nogpgcheck -y install libsgx-urts libsgx-launch libsgx-epid libsgx-quote-ex libsgx-dcap-ql libsgx-uae-service libsgx-dcap-quote-verify-devel
RUN yum -y groupinstall 'Development Tools'

# COPY patches/libsgx_dcap_quoteverify.so  /usr/lib64/
RUN yum -y install --nogpgcheck sgx-dcap-pccs libsgx-dcap-default-qpl

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

RUN yum -y install gawk bison python3-click python3-jinja2 golang ninja-build
RUN yum -y install openssl-devel protobuf-c-devel python3-protobuf protobuf-c-compiler protobuf-compiler

RUN yum -y install gmp-devel mpfr-devel libmpc-devel isl-devel nasm python3-devel mailcap

RUN ln -s /usr/bin/python3 /usr/bin/python \
    && python3 -m pip install --upgrade pip \
    && python3 -m pip install toml meson wheel cryptography paramiko numpy pyelftools


RUN rm -rf ${GRAMINEDIR} && git clone https://github.com/gramineproject/gramine.git ${GRAMINEDIR} \
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

#tensorflow_model_server
RUN cd /usr/bin && curl -fLO https://releases.bazel.build/3.7.2/release/bazel-3.7.2-linux-x86_64 && chmod +x bazel-3.7.2-linux-x86_64
RUN git clone https://github.com/tensorflow/serving.git \
    && cd serving \
    && git checkout 2.6.2 \
    && bazel-3.7.2-linux-x86_64 build -c opt //tensorflow_serving/model_servers:tensorflow_model_server
RUN cp serving/bazel-bin/tensorflow_serving/model_servers/tensorflow_model_server /usr/bin

# Clean apt cache
RUN yum -y clean all && rm -rf /var/cache

# Build Secret Provision
ENV RA_TYPE=dcap
RUN cd ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov \
    && make app ${RA_TYPE} RA_TYPE=${RA_TYPE}

COPY ca.crt ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov/ssl

WORKDIR ${WORK_BASE_PATH}

RUN cp ${GRAMINEDIR}/build/tools/sgx/ra-tls/libsecret_prov_attest.so . \
    && cp -R ${GRAMINEDIR}/CI-Examples/ra-tls-secret-prov/ssl .

COPY anolisos/Makefile .
COPY anolisos/tensorflow_model_server.manifest.template .
RUN make SGX=${SGX} RA_TYPE=${RA_TYPE} -j `nproc` | grep "mr_enclave\|mr_signer\|isv_prod_id\|isv_svn" | tee -a enclave.mr

COPY tf_serving_entrypoint.sh /usr/bin
COPY sgx_default_qcnl.conf /etc/sgx_default_qcnl.conf

# Expose tensorflow-model-server ports
# gRPC
EXPOSE 8500
# REST
EXPOSE 8501

RUN chmod +x /usr/bin/tf_serving_entrypoint.sh
RUN cat /etc/sgx_default_qcnl.conf
ENTRYPOINT ["/usr/bin/tf_serving_entrypoint.sh"]