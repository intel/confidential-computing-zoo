#!/bin/bash

set -e

if  [ -n "$1" ] ; then
    export VFS_PATH=$1
else
    export VFS_PATH=/root/vfs
fi

if  [ -n "$2" ] ; then
    export VFS_SIZE=$2
else
    export VFS_SIZE=1G
fi

if  [ -n "$3" ] ; then
    export key_path=$3
fi

if  [ -n "$4" ] ; then
    export map=$4
else
    export map=123456789
fi


# create virtual volume
truncate -s "$VFS_SIZE" "$VFS_PATH"
echo "Create ${VFS_SIZE} block file at ${VFS_PATH}"

# bind loop device to virtual volume
LOOP_DEVICE=$5
if losetup -j "$VFS_PATH" | grep -q "^$LOOP_DEVICE:"; then
    echo "Reuse loop device ${LOOP_DEVICE} for ${VFS_PATH}"
else
    losetup "$LOOP_DEVICE" "$VFS_PATH"
    echo "Bind ${VFS_PATH} to loop device ${LOOP_DEVICE}"
fi

# encrypt loop device in luks format, press "YES"
cryptsetup --debug -v luksFormat -s 512 -c aes-xts-plain64 ${LOOP_DEVICE} --batch-mode --key-file ${key_path}
echo "Encrypt loop device ${LOOP_DEVICE} done"

# luksOpen mapper
MAPPER_PATH="/dev/mapper/$map"

echo "luksOpen ${LOOP_DEVICE} to luks mapper ${MAPPER_PATH} via password"
cryptsetup luksOpen ${LOOP_DEVICE} $map --key-file ${key_path}

echo "Format ${MAPPER_PATH} to ext4"
mkfs.ext4 "$MAPPER_PATH"
sleep 5
echo "luksClose ${MAPPER_PATH} via password"
cryptsetup luksClose "$MAPPER_PATH" || true

losetup -d "$LOOP_DEVICE"
echo "Unbind ${LOOP_DEVICE}"
