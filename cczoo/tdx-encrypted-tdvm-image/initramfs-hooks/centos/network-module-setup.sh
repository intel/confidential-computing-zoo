#!/bin/bash

check() {
  return 0
}

depends() {
  return 0
}

install() {
  cp -rf /root/resolv.conf "$initdir/etc/"
}

