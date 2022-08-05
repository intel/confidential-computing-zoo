## gRPC supporting Intel RA-TLS

### Source env

```
source ./env
```

### Install cmake

```
mkdir -p ${INSTALL_PREFIX}
wget -q -O cmake-linux.sh https://github.com/Kitware/CMake/releases/download/v3.19.6/cmake-3.19.6-Linux-x86_64.sh
sh cmake-linux.sh -- --skip-license --prefix=${INSTALL_PREFIX}
rm cmake-linux.sh
```

### Prepare code

```
./prepare_code.sh
pip3 install --upgrade pip
pip3 install -r ${GRPC_PATH}/requirements.txt
```

### Build code

- c++

    refer to `grpc/src/examples/cpp/ra-tls`

- python

    refer to `grpc/src/examples/python/ra-tls`
