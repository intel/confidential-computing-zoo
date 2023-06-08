## RA-TLS Enhanced gRPC based on Intel TDX

## How to Build

1. Build tdx-dev docker image

    Please review the following document

    - cczoo/common/docker/tdx/README.md

2. Build grpc-ratls-dev docker image

    Execute the following command to build this docker image

    ```
    base_image=tdx-dev:dcap1.15-centos8-latest
    image_tag=grpc-ratls-dev:tdx-dcap1.15-centos8-latest
    ./build_docker_image.sh ${base_image} ${image_tag}
    ```

## How to run gRPC examples

1. start container in `TDX Guest OS`

    Pull docker image in `TDX Guest OS`, and exec the following command:

    ```
    cczoo/grpc-ra-tls/tdx/start_container.sh ${pccs_service_ip} ${image_tag}
    ```

2. Start aesm service

    ```
    /root/start_aesm_service.sh
    ```

3. build and run gRPC examples

    ```
    export SGX_RA_TLS_BACKEND=TDX
    ```

    - c++

        ${GRPC_PATH}/examples/cpp/ratls/README.md

        ```
        cd ${GRPC_PATH}/examples/cpp/ratls
        ./build.sh
        cd build
        ./server &
        ./client
        ```

    - python

         ${GRPC_PATH}/examples/cpp/python/README.md

        ```
        cd ${GRPC_PATH}/examples/python/ratls
        ./build.sh
        cd build
        python3 -u ./server.py &
        python3 -u ./client.py
        ```
