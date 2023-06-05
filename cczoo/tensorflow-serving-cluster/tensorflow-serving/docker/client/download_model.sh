#
# Copyright (c) 2021 Intel Corporation
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

#!/usr/bin/env bash

set -e

cur_dir=`pwd -P`
models_abs_dir=${cur_dir}/models
mkdir -p ${models_abs_dir}

# resnet50-v15
mkdir -p ${models_abs_dir}/resnet50-v15-fp32
cd ${models_abs_dir}/resnet50-v15-fp32
wget https://storage.googleapis.com/intel-optimized-tensorflow/models/v1_8/resnet50_fp32_pretrained_model.pb -O resnet50-v15-fp32.pb
