#!/bin/bash

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

set -e

if  [ -n "$1" ] ; then
    export VFS_PATH=$1
else
    export VFS_PATH=/root/vfs
fi

if  [ -n "$2" ] ; then
    export MOUNT_PATH=$2
else
    export MOUNT_PATH=/mnt/luks_fs
fi

if  [ -n "$3" ] ; then
    export map=$3
else
    export map=123456789
fi

if  [ -n "$4" ] ; then
    export key_path=$4
fi

# bind loop device to virtual volume
LOOP_DEVICE=$5
if losetup -j "$VFS_PATH" | grep -q "^$LOOP_DEVICE:"; then
    echo "Reuse loop device ${LOOP_DEVICE} for ${VFS_PATH}"
else
    losetup "$LOOP_DEVICE" "$VFS_PATH"
    echo "Bind ${VFS_PATH} to loop device ${LOOP_DEVICE}"
fi

# luksOpen mapper
MAPPER_PATH=/dev/mapper/${map}

if  [ "$6" = "" ]; then
    echo "luksOpen ${LOOP_DEVICE} to luks mapper ${MAPPER_PATH} via password"
    cryptsetup luksOpen ${LOOP_DEVICE} ${map}  --key-file ${key_path}
else
    echo "luksOpen ${LOOP_DEVICE} to luks mapper ${MAPPER_PATH} via secretmanager service"
    cd "$(dirname "$0")/get_secret/runtime/ra-client"
    APP_ID=$6
    TRY_MAX_NUM=5
    try_count=0
    while [ "$try_count" != "$TRY_MAX_NUM" ]
    do
        PASSWORD=$(no_proxy="$noproxy,localhost" LD_LIBRARY_PATH=usr/lib GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=usr/bin/roots.pem usr/bin/ra-client -host="$RA_SERVICE_ADDRESS" -key="$APP_ID" | grep 'Secret' | awk -F ': ' '{print $2}')
        if [ "$PASSWORD" == "RPC failed" ]; then
            try_count=$((try_count + 1))
        else
            break
        fi
    done
    cd -
    # echo "Get Password via gRPC-RA-TLS, APP_ID: ${APP_ID} -> PASSWORD: ${PASSWORD}"
    printf '%s\n' "$PASSWORD" | cryptsetup luksOpen "$LOOP_DEVICE" "$map"
fi

mkdir -p "$MOUNT_PATH"
mount "$MAPPER_PATH" "$MOUNT_PATH"
ls -al "$MOUNT_PATH"
