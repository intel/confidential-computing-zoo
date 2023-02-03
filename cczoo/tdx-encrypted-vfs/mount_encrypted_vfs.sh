set -e

if  [ -n "$1" ] ; then
    LOOP_DEVICE=$1
else
    LOOP_DEVICE=$(losetup -f)
fi
echo "Idle Loop Device: "${LOOP_DEVICE}

if  [ -n "$2" ] ; then
    FS_DIR=$2
else
    FS_DIR=luks_fs
fi

if  [ "$4" = "" ]; then
    cryptsetup luksOpen ${LOOP_DEVICE} ${FS_DIR}
else
    cd `dirname $0`
    TDX_ID=tdx
    PASSWORD=`get_secret/client -host=${hostname} -key=${TDX_ID} | grep "Secret" | awk '{print $3}'`
    echo "Get VFS Password via gRPC-RA-TLS, ID: ${TDX_ID} -> PASSWORD: ${PASSWORD}"
    echo ${PASSWORD} | cryptsetup luksOpen ${LOOP_DEVICE} ${FS_DIR}
    cd -
fi
ls -al /dev/mapper/${FS_DIR}

if  [ "$3" = "format" ]; then
    mkfs.ext4 /dev/mapper/${FS_DIR}
fi

mkdir -p /mnt/${FS_DIR}
mount /dev/mapper/${FS_DIR} /mnt/${FS_DIR}

ls /mnt/${FS_DIR}
