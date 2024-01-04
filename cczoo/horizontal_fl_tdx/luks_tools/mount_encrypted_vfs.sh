#!/bin/bash
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

set -e

if  [ -n "$1" ] ; then
    LOOP_DEVICE=$1
else
    LOOP_DEVICE=$(losetup -f)
fi
echo ${LOOP_DEVICE}

if  [ -n "$3" ] ; then
    FS_DIR=$3
else
    FS_DIR=model
fi

cryptsetup luksOpen ${LOOP_DEVICE} ${FS_DIR}

ls -al /dev/mapper/${FS_DIR}

if  [ "$2" = "format" ]; then
    mkfs.ext4 /dev/mapper/${FS_DIR}
fi

mount /dev/mapper/${FS_DIR} /hfl-tensorflow/model

df -h /hfl-tensorflow/model
