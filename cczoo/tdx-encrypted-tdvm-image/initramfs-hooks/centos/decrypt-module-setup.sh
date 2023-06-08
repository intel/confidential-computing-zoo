#!/bin/bash

check() {
  return 0
}

depends() {
  return 0
}

install() {
  inst_hook initqueue/finished 99 "$moddir/opening_disk.sh"
}
