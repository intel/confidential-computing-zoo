#!/usr/bin/env bash

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

#!/usr/bin/env bash

set -ex

# Default args
model_name="resnet50-v15-fp32"
enable_batching=false
rest_api_num_threads=64
session_parallelism=0
parallel_num_threads=8
file_system_poll_wait_seconds=5
vfs_path=/mnt/luks_fs
image_tag=tf-serving-dev:latest

function usage_help() {
    echo -e "options:"
    echo -e "  -h Display help"
    echo -e "  -i {image_tag}"
    echo -e "  -m {model_name}"
    echo -e "  -v {vfs_path}"
}

# Override args
while getopts "h?r:i:m:v:" OPT; do
    case $OPT in
        h|\?)
            usage_help
            exit 1
            ;;
        i)
            echo -e "Option $OPTIND, image_tag = $OPTARG"
            image_tag=$OPTARG
            ;;
        m)
            echo -e "Option $OPTIND, model_name = $OPTARG"
            model_name=$OPTARG
            ;;
        v)
            echo -e "Option $OPTIND, vfs_path = $OPTARG"
            vfs_path=$OPTARG
            ;;
        :)
            echo -e "Option $OPTARG needs argument"
            usage_help
            exit 1
            ;;
        ?)
            echo -e "Unknown option $OPTARG"
            usage_help
            exit 1
            ;;
    esac
done

env

docker run \
    -itd \
    --net=host \
    -v ${vfs_path}:/vfs \
    -e model_name=${model_name} \
    -e enable_batching=${enable_batching} \
    -e rest_api_num_threads=${rest_api_num_threads} \
    -e session_parallelism=${session_parallelism} \
    -e intra_op_parallelism=${parallel_num_threads} \
    -e inter_op_parallelism=${parallel_num_threads} \
    -e OMP_NUM_THREADS=${parallel_num_threads} \
    -e MKL_NUM_THREADS=${parallel_num_threads} \
    -e file_system_poll_wait_seconds=${file_system_poll_wait_seconds} \
    ${image_tag}
