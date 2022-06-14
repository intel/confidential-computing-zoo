if [ ! -d "${GRPC_PATH}" ]; then
    git clone --recurse-submodules -b ${GRPC_VERSION} https://github.com/grpc/grpc ${GRPC_PATH}
fi

export CUR_DIR=`dirname "$0"`
cp -r ${CUR_DIR}/../grpc/common/* ${GRPC_PATH}
cp -r ${CUR_DIR}/../grpc/${GRPC_VERSION}/* ${GRPC_PATH}
