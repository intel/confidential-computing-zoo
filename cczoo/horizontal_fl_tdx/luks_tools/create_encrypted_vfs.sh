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

set -ex

if  [ -n "$1" ] ; then
    VIRTUAL_FS=$1
else
    VIRTUAL_FS=/root/vfs
fi
echo ${VIRTUAL_FS}

# create virtual volume
truncate -s 1G ${VIRTUAL_FS}

export LOOP_DEVICE=$(losetup -f)
echo ${LOOP_DEVICE}

# bind loop device to virtual volume
losetup ${LOOP_DEVICE} ${VIRTUAL_FS}

# encrypt loop device in luks format, press "YES"
cryptsetup --debug -y -v luksFormat -s 512 -c aes-xts-plain64 ${LOOP_DEVICE}

echo "LOOP_DEVICE=${LOOP_DEVICE}"
