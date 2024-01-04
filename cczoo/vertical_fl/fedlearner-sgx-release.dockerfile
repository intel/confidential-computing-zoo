ARG base_image=fedlearner-sgx-dev:latest

FROM ${base_image} AS builder

RUN cd ${GRPC_PATH} \
    && rm -rf .git build python_build

RUN cd ${GRAMINEDIR} \
    && rm -rf .git subprojects build

RUN rm -rf ${TF_PATH}

RUN apt-get clean all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/* \
    && rm -rf /tmp/*

RUN unset PWD HOSTNAME http_proxy https_proxy no_proxy \
    && env | tee -a ~/.env \
    && sed -i "s/^/export ${i}\t&/g" ~/.env \
    && echo "source ~/.env" >> ~/.bashrc

FROM scratch

COPY --from=builder / /


EXPOSE 6006 50051 50052

RUN chmod +x /root/entrypoint.sh
# ENTRYPOINT ["/root/entrypoint.sh"]
