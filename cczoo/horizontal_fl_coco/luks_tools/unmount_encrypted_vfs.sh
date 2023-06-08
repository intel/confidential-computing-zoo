set -e

MOUNT_PATH=$1
MAPPER_PATH=$2
LOOP_DEVICE=$3

echo "unmount ${MOUNT_PATH}"
umount ${MOUNT_PATH} || true
# fuser -cuk ${MOUNT_PATH} || true

echo "luksClose ${MAPPER_PATH} via password"
cryptsetup luksClose ${MAPPER_PATH} || true

losetup -d ${LOOP_DEVICE} || true
echo "Unbind ${LOOP_DEVICE}"
