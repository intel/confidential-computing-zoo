#!/bin/sh

# Saved for RA
key=`/sbin/getting_key.sh`

echo ${key} | cryptsetup luksOpen  /dev/vda3 luks-rootfs

