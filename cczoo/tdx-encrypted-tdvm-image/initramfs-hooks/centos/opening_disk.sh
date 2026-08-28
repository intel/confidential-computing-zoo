#!/bin/sh

set -eu

cleanup_unlock()
{
        /sbin/tdvm-security.sh close-luks
}

/sbin/tdvm-security.sh validate-cmdline
/sbin/tdvm-security.sh validate-td

if ! /sbin/getting_key.sh | cryptsetup luksOpen --key-file=- /dev/vda3 luks-rootfs; then
        cleanup_unlock
        echo "tdvm-security: unlocking failed" > /dev/console
        exit 1
fi

if [ ! -e "/dev/mapper/luks-rootfs" ]; then
        cleanup_unlock
        echo  "luks rootfs dm target not found" > /dev/console
        exit 1
fi

exit 0
