set -e

if  [ -n "$1" ] ; then
    export VIRTUAL_FS=$1
else
    export VIRTUAL_FS=/root/vfs
fi

if  [ -n "$2" ] ; then
    export VFS_SIZE=$2
else
    export VFS_SIZE=1G
fi

# create virtual volume
truncate -s ${VFS_SIZE} ${VIRTUAL_FS}
echo "Create ${VFS_SIZE} block file at ${VIRTUAL_FS}"

# bind loop device to virtual volume
LOOP_DEVICE=$(losetup -f)
losetup ${LOOP_DEVICE} ${VIRTUAL_FS}
echo "Bind ${VIRTUAL_FS} to loop device ${LOOP_DEVICE}"

# encrypt loop device in luks format, press "YES"
cryptsetup --debug -y -v luksFormat -s 512 -c aes-xts-plain64 ${LOOP_DEVICE}
echo "Encrypt loop device ${LOOP_DEVICE} done"

# luksOpen mapper
MAPPER_DIR=$RANDOM$RANDOM$RANDOM$RANDOM
MAPPER_PATH=/dev/mapper/${MAPPER_DIR}

echo "luksOpen ${LOOP_DEVICE} to luks mapper ${MAPPER_PATH} via password"
cryptsetup luksOpen ${LOOP_DEVICE} ${MAPPER_DIR}

echo "Format ${MAPPER_PATH} to ext4"
mkfs.ext4 ${MAPPER_PATH}

echo "luksClose ${MAPPER_PATH} via password"
cryptsetup luksClose ${MAPPER_PATH} || true

losetup -d ${LOOP_DEVICE}
echo "Unbind ${LOOP_DEVICE}"
