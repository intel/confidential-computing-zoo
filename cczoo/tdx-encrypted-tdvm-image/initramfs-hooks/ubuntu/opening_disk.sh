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
	exit 1
fi

[ -e "/dev/mapper/luks-rootfs" ] || {
	cleanup_unlock
	exit 1
}

