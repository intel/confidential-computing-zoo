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

usage() {
    echo "Usage: $0 {create|mount|unmount} ..." >&2
    exit 2
}

create_vfs() {
    local vfs_path=$1
    local vfs_size=$2
    local key_path=$3
    local map=$4
    local loop_device=$5

    truncate -s "$vfs_size" "$vfs_path"
    echo "Create ${vfs_size} block file at ${vfs_path}"

    if losetup -j "$vfs_path" | grep -q "^$loop_device:"; then
        echo "Reuse loop device ${loop_device} for ${vfs_path}"
    else
        losetup "$loop_device" "$vfs_path"
        echo "Bind ${vfs_path} to loop device ${loop_device}"
    fi

    cryptsetup --debug -v luksFormat -s 512 -c aes-xts-plain64 "$loop_device" --batch-mode --key-file "$key_path"
    echo "Encrypt loop device ${loop_device} done"

    local mapper_path="/dev/mapper/$map"
    echo "luksOpen ${loop_device} to luks mapper ${mapper_path} via password"
    cryptsetup luksOpen "$loop_device" "$map" --key-file "$key_path"

    echo "Format ${mapper_path} to ext4"
    mkfs.ext4 "$mapper_path"
    sleep 5
    echo "luksClose ${mapper_path} via password"
    cryptsetup luksClose "$mapper_path" || true

    losetup -d "$loop_device"
    echo "Unbind ${loop_device}"
}

mount_vfs() {
    local vfs_path=$1
    local mount_path=$2
    local map=$3
    local key_path=$4
    local loop_device=$5
    local app_id=$6

    if losetup -j "$vfs_path" | grep -q "^$loop_device:"; then
        echo "Reuse loop device ${loop_device} for ${vfs_path}"
    else
        losetup "$loop_device" "$vfs_path"
        echo "Bind ${vfs_path} to loop device ${loop_device}"
    fi

    local mapper_path="/dev/mapper/${map}"
    if [ -z "$app_id" ]; then
        echo "luksOpen ${loop_device} to luks mapper ${mapper_path} via password"
        cryptsetup luksOpen "$loop_device" "$map" --key-file "$key_path"
    else
        echo "luksOpen ${loop_device} to luks mapper ${mapper_path} via secretmanager service"
        local runtime_dir="$(dirname "$0")/get_secret/runtime/ra-client"
        local password
        local try_max_num=5
        local try_count=0
        while [ "$try_count" != "$try_max_num" ]; do
            password=$(cd "$runtime_dir" && no_proxy="$noproxy,localhost" LD_LIBRARY_PATH=usr/lib GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=usr/bin/roots.pem usr/bin/ra-client -host="$RA_SERVICE_ADDRESS" -key="$app_id" | grep 'Secret' | awk -F ': ' '{print $2}')
            if [ "$password" = "RPC failed" ]; then
                try_count=$((try_count + 1))
            else
                break
            fi
        done
        printf '%s\n' "$password" | cryptsetup luksOpen "$loop_device" "$map"
    fi

    mkdir -p "$mount_path"
    mount "$mapper_path" "$mount_path"
    ls -al "$mount_path"
}

unmount_vfs() {
    local mount_path=$1
    local mapper_path=$2
    local loop_device=$3

    echo "unmount ${mount_path}"
    umount "$mount_path" || true

    echo "luksClose ${mapper_path} via password"
    cryptsetup luksClose "$mapper_path" || true

    losetup -d "$loop_device" || true
    echo "Unbind ${loop_device}"
}

case "$1" in
    create)
        [ "$#" -eq 6 ] || usage
        create_vfs "$2" "$3" "$4" "$5" "$6"
        ;;
    mount)
        [ "$#" -eq 6 ] || [ "$#" -eq 7 ] || usage
        mount_vfs "$2" "$3" "$4" "$5" "$6" "${7:-}"
        ;;
    unmount)
        [ "$#" -eq 4 ] || usage
        unmount_vfs "$2" "$3" "$4"
        ;;
    *)
        usage
        ;;
esac