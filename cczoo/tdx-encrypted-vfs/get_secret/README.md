## get_secret service based on RA-TLS Enhanced gRPC

### Build docker image

```
base_image=centos:8
image_tag=grpc-ratls-secretmanger-dev:tdx-dcap1.15-centos8-latest
./build_docker_image.sh $base_image $image_tag
```

### Prepare runtime

prepare for the runtime for `mount_encrypted_vfs.sh`

```
./prepare_runtime.sh
```

### Start service

1. start service container in Host

    ```
    ./start_container.sh <PCCS_ADDRESS>
    ```

2. Add your <APP_ID>:<PASSWORD> pair to `secret.json` in container.

    ```
    docker exec -it secretmanger bash
    vim ${WORK_SPACE_PATH}/build/secret.json
    ```

3. restart service container

    ```
    docker restart secretmanger
    ```

### Test service

- Test in guest:

    ```
    APP_ID=app1
    RA_SERVICE_ADDRESS=localhost:50051
    RUNTIME_DIR=runtime/ra-client
    TRY_MAX_NUM=5

    cd $RUNTIME_DIR
    try_count=0
    while [ "$try_count" != "$TRY_MAX_NUM" ]
    do
        PASSWORD=`no_proxy=$noproxy,localhost LD_LIBRARY_PATH=usr/lib GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=usr/bin/roots.pem usr/bin/ra-client -host=$RA_SERVICE_ADDRESS -key=$APP_ID | grep 'Secret' | awk -F ': ' '{print $2}'`
        if [ "$PASSWORD" == "RPC failed" ]; then
            try_count=$((try_count + 1))
        else
            echo $PASSWORD
            break
        fi
    done
    cd -
    ```

- Test in guest docker:

    ```
    docker exec -it secretmanger bash

        cd ${WORK_SPACE_PATH}/build
        GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=$GRPC_PATH/etc/roots.pem \
        ./client \
            -host=localhost:50051 \
            -cfg=/usr/bin/dynamic_config.json \
            -key=<APP_ID>
    ```
