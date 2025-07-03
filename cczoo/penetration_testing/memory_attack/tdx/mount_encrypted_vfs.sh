set -e

VFS_PATH=/root/vfs
MOUNT_PATH=/mnt/luks_fs

# bind loop device to virtual volume
LOOP_DEVICE=$(losetup -f)
losetup ${LOOP_DEVICE} ${VFS_PATH}
echo "Bind ${VFS_PATH} to loop device ${LOOP_DEVICE}"

# luksOpen mapper
MAPPER_DIR=$RANDOM$RANDOM$RANDOM$RANDOM
MAPPER_PATH=/dev/mapper/${MAPPER_DIR}

#For demo purpose, the key is used by default.
echo "luks@luks123" | cryptsetup luksOpen ${LOOP_DEVICE} ${MAPPER_DIR}

mkdir -p ${MOUNT_PATH}
mount ${MAPPER_PATH} ${MOUNT_PATH}
ls -al ${MOUNT_PATH}

# Run key generator
python3 /mnt/luks_fs/key_generator.py