#!/bin/bash

check() {
    return 0
}

depends() {
    return 0
}

install() {
    cp -rf /sbin/getting_key.sh "$initdir/sbin/"
    cp -rf /ra-client/usr/bin/* "$initdir/usr/bin/"
    cp -f /ra-client/etc/hosts "$initdir/etc/"
    cp -rf /ra-client/usr/lib/* "$initdir/usr/lib/"

    inst_binary="/sbin/cryptsetup"
    inst "/sbin/cryptsetup"
    #inst_multiple dmsetup udev udevadm
}
