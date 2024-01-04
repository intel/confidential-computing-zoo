set -e

if  [ -n "$1" ] ; then
    export VFS_PATH=$1
else
    export VFS_PATH=/root/vfs
fi

if  [ -n "$2" ] ; then
    export MOUNT_PATH=$2
else
    export MOUNT_PATH=/mnt/luks_fs
fi

# bind loop device to virtual volume
LOOP_DEVICE=$(losetup -f)
losetup ${LOOP_DEVICE} ${VFS_PATH}
echo "Bind ${VFS_PATH} to loop device ${LOOP_DEVICE}"

# luksOpen mapper
MAPPER_DIR=$RANDOM$RANDOM$RANDOM$RANDOM
MAPPER_PATH=/dev/mapper/${MAPPER_DIR}

if  [ "$3" == "" ]; then
    echo "luksOpen ${LOOP_DEVICE} to luks mapper ${MAPPER_PATH} via password"
    cryptsetup luksOpen ${LOOP_DEVICE} ${MAPPER_DIR}
else
    echo "luksOpen ${LOOP_DEVICE} to luks mapper ${MAPPER_PATH} via secretmanager service"
    cd `dirname $0`/get_secret/runtime/ra-client
    APP_ID=$3
    TRY_MAX_NUM=5
    try_count=0
    while [ "$try_count" != "$TRY_MAX_NUM" ]
    do
        PASSWORD=`no_proxy=$noproxy,localhost LD_LIBRARY_PATH=usr/lib GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=usr/bin/roots.pem usr/bin/ra-client -host=$RA_SERVICE_ADDRESS -key=$APP_ID | grep 'Secret' | awk -F ': ' '{print $2}'`
        if [ "$PASSWORD" == "RPC failed" ]; then
            try_count=$((try_count + 1))
        else
            break
        fi
    done
    cd -
    # echo "Get Password via gRPC-RA-TLS, APP_ID: ${APP_ID} -> PASSWORD: ${PASSWORD}"
    echo ${PASSWORD} | cryptsetup luksOpen ${LOOP_DEVICE} ${MAPPER_DIR}
fi

mkdir -p ${MOUNT_PATH}
mount ${MAPPER_PATH} ${MOUNT_PATH}
ls -al ${MOUNT_PATH}
