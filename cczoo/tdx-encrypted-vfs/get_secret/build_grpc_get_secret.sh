set -ex

if [ ! -d "${GRPC_PATH}" ]; then
   git clone --recurse-submodules -b ${GRPC_VERSION} https://github.com/grpc/grpc ${GRPC_PATH}
    cp -r *.patch ${GRPC_PATH}
    cd ${GRPC_PATH}
    git apply *.patch
    cd -
fi

cd ${GRPC_PATH}/examples/cpp/secretmanger
./build.sh
