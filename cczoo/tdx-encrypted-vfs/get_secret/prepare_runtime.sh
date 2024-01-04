set -e

if  [ -n "$1" ] ; then
    image_tag=$1
else
    image_tag=grpc-ratls-secretmanger-dev:tdx-dcap1.15-centos8-latest
fi

if  [ -n "$2" ] ; then
    image_name=$2
else
    image_name=secretmanger-runtime
fi

grpc_path=/grpc/src
work_dir=$grpc_path/examples/cpp/secretmanger/build
runtime_dir=`pwd -P`/runtime
mkdir -p $runtime_dir

# copy runtime from
docker rm -f $image_name || true
docker run -d --name=$image_name $image_tag
docker cp $image_name:$work_dir $runtime_dir
docker cp $image_name:$grpc_path/etc/roots.pem $runtime_dir/build
docker cp $image_name:/usr/lib64/libsgx_enclave_common.so.1 $runtime_dir/build
docker cp $image_name:/usr/lib64/libsgx_urts.so.2 $runtime_dir/build

docker rm -f $image_name || true

# prepare runtime dir
mkdir -p $runtime_dir/{ra-client,ra-server}
mkdir -p $runtime_dir/ra-client/{etc,usr/bin,usr/lib}

# ra-server
cp -r $runtime_dir/build/{server,*.json,roots.pem} $runtime_dir/ra-server
mv $runtime_dir/ra-server/server $runtime_dir/ra-server/ra-server

# ra-client
cp -r $runtime_dir/build/{client,*.json,roots.pem} $runtime_dir/ra-client/usr/bin
cp -r $runtime_dir/build/libsgx_enclave_common.so* $runtime_dir/ra-client/usr/lib/libsgx_enclave_common.so.1
cp -r $runtime_dir/build/libsgx_urts.so* $runtime_dir/ra-client/usr/lib/libsgx_urts.so.2
mv $runtime_dir/ra-client/usr/bin/client $runtime_dir/ra-client/usr/bin/ra-client

rm -rf $runtime_dir/build

echo "prepare runtime done!"
