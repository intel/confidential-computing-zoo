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
