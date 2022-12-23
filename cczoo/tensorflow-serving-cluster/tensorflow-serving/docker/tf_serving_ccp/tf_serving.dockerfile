FROM ubuntu:20.04

ENV WORK_BASE_PATH=/
ENV MODEL_BASE_PATH=${WORK_BASE_PATH}/models
ENV MODEL_NAME=model
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

RUN apt-get update \
    && apt-get install -y curl

ARG TF_SERVING_PKGNAME=tensorflow-model-server
ARG TF_SERVING_VERSION=2.6.2
RUN curl -LO https://storage.googleapis.com/tensorflow-serving-apt/pool/${TF_SERVING_PKGNAME}-${TF_SERVING_VERSION}/t/${TF_SERVING_PKGNAME}/${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb \
    && apt-get install -y ./${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb


# COPY ${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb ${WORK_BASE_PATH}
# RUN dpkg -i ./${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb \
#     && rm -f ${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb

COPY models ${MODEL_BASE_PATH}
COPY ssl_configure/ssl.cfg  ${WORK_BASE_PATH}
COPY ssl ${WORK_BASE_PATH}
COPY tf_serving_entrypoint.sh /usr/bin

RUN chmod +x /usr/bin/tf_serving_entrypoint.sh
ENTRYPOINT ["/usr/bin/tf_serving_entrypoint.sh"]
