#!/bin/sh

# Saved for RA
key=`/sbin/getting_key.sh`
echo ${key} | cryptsetup luksOpen  /dev/vda3 luks-rootfs
if [ ! -e "/dev/mapper/luks-rootfs" ]; then
        echo  "luks rootfs dm target not found" > /dev/console
fi

exit 0
