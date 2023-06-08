# RA-TLS Enhanced gRPC based on Occlum-SGX

## How to Build

1. Build occlum-sgx-dev docker image

    Please review the following document

    - cczoo/common/docker/occlum/README.md

2. Build grpc-ratls-dev docker image

    Execute the following command to build this docker image

    ```
    base_image=occlum-sgx-dev:0.26.3-ubuntu20.04-latest
    image_tag=grpc-ratls-dev:occlum0.26.3-ubuntu20.04-latest
    ./build_docker_image.sh ${base_image} ${image_tag}
    ```

## How to run gRPC examples

1. start container

    ```
    cczoo/grpc-ra-tls/occlum/start_container.sh ${pccs_service_ip} ${image_tag}
    ```

2. Start aesm service

    ```
    /root/start_aesm_service.sh
    ```

3. build and run gRPC examples

    ```
    export SGX_RA_TLS_BACKEND=OCCLUM
    ```

    - c++

        ${OCCLUM_PATH}/demos/ratls/README.md
