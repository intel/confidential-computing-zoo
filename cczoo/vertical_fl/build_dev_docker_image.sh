#!/bin/bash
set -e

if  [ ! -n "$1" ] ; then
    image_tag=latest
else
    image_tag=$1
fi

if  [ -z "$AZURE" ] ; then
    azure=
else
    azure=1
fi

# Use the host proxy as the default configuration, or specify a proxy_server
# no_proxy="localhost,127.0.0.1"
# proxy_server="" # your http proxy server

if [ "$proxy_server" != "" ]; then
    http_proxy=${proxy_server}
    https_proxy=${proxy_server}
fi

DOCKER_BUILDKIT=0 docker build \
    -f fedlearner-sgx-dev.dockerfile \
    -t fedlearner-sgx-dev:${image_tag} \
    --build-arg http_proxy=${http_proxy} \
    --build-arg https_proxy=${https_proxy} \
    --build-arg no_proxy=${no_proxy} \
    --build-arg AZURE=${azure} \
    .
