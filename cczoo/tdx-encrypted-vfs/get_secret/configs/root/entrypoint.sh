#
# Copyright (c) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#!/bin/bash
set -e

cd ${GRPC_PATH}/examples/cpp/secretmanger/build

http_proxy= \
https_proxy= \
HTTP_PROXY= \
HTTPS_PROXY= \
GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=/usr/local/share/grpc/roots.pem \
./server -host=0.0.0.0:50051 -cfg=dynamic_config.json -s=secret.json

cd -
