#!/bin/bash
#
# Copyright (c) 2026 Intel Corporation
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
    FS_DIR=$1
else
    FS_DIR=model
fi

if  [ -n "$2" ] ; then
    MOUNT_POINT=$2
else
    MOUNT_POINT=/home/encrypted_storage
fi

umount ${MOUNT_POINT} || { echo 'umount failed' ; exit 1; }
cryptsetup luksClose /dev/mapper/${FS_DIR} || { echo 'luksClose operation failed' ; exit 1; }
