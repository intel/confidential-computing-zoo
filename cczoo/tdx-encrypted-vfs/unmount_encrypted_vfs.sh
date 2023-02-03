set -ex

if  [ -n "$1" ] ; then
    VIRTUAL_FS=$1
else
    VIRTUAL_FS=/root/vfs
fi
echo ${VIRTUAL_FS}

if  [ -n "$2" ] ; then
    FS_DIR=$2
else
    FS_DIR=luks_fs
fi

umount /mnt/${FS_DIR} || true
# fuser -cuk /mnt/${FS_DIR} || true
cryptsetup luksClose /dev/mapper/${FS_DIR} || true
