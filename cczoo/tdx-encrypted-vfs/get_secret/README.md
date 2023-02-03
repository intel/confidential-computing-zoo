## get_secret service based on gRPC supporting Intel RA-TLS

### Setup environment

Please refer to `grpc-ra-tls/tdx/README.md` for detail.

### Build code

```
source ../../../grpc-ra-tls/tdx/env
./build_grpc_get_secret.sh
```

### Copy runtime

- client
    prepare for the client of `mount_encrypted_vfs.sh`

    ```
    cp ${GRPC_PATH}/examples/cpp/secretmanger/build/client .
    ```

- server

    prepare for the server of `mount_encrypted_vfs.sh`

    ```
    cp ${GRPC_PATH}/examples/cpp/secretmanger/build/server .
    cp ${GRPC_PATH}/examples/cpp/secretmanger/build/*.json .
    ```

### Start service

    Add your <key name> <value> pair to `secret.json`, then

    ```
    hostname=localhost:50051
    ./server -host=${hostname} &
    ```

### Get secret

    ```
    hostname=localhost:50051
    ./client -host=${hostname} -key=<key name>
    ```
