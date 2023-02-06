#
# Copyright (c) 2023 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM ubuntu:20.04

# Add steps here to set up dependencies
RUN apt-get update \
    && apt-get install -y curl gnupg2 \
    && apt-get install -y --no-install-recommends apt-utils

# # Add TensorFlow Serving distribution URI as a package source
# RUN echo "deb [trusted=yes arch=amd64] http://storage.googleapis.com/tensorflow-serving-apt stable tensorflow-model-server tensorflow-model-server-universal" | tee /etc/apt/sources.list.d/tensorflow-serving.list \
#     && curl https://storage.googleapis.com/tensorflow-serving-apt/tensorflow-serving.release.pub.gpg | apt-key add -

# # Install the latest tensorflow-model-server
# RUN apt-get update \
#     && apt-cache madison "tensorflow-model-server" \
#     && apt-get install -y tensorflow-model-server \
#     && apt-get clean all

ARG TF_SERVING_PKGNAME=tensorflow-model-server
ARG TF_SERVING_VERSION=2.6.2
RUN curl -LO https://storage.googleapis.com/tensorflow-serving-apt/pool/${TF_SERVING_PKGNAME}-${TF_SERVING_VERSION}/t/${TF_SERVING_PKGNAME}/${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb \
    && apt-get install -y ./${TF_SERVING_PKGNAME}_${TF_SERVING_VERSION}_all.deb

COPY tf_serving_entrypoint.sh /usr/bin
RUN chmod +x /usr/bin/tf_serving_entrypoint.sh

# Expose tensorflow-model-server gRPC and REST ports
EXPOSE 8500 8501

ENTRYPOINT ["/usr/bin/tf_serving_entrypoint.sh"]
