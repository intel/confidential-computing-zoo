# GRPC-RATLS-SGX-Dev Docker Image

## How to Build

1. Get occlum docker image

    Please review the following document

    - cczoo/common/docker/occlum/README.md

2. Build grpc-ratls-sgx-dev docker image

    Execute the following command to build this docker image

    ```
    ./build_docker_image.sh
    ```

## How to run gRPC examples

1. start container

    ```
    cczoo/grpc-ra-tls/start_container.sh ${pccs_service_ip} ${image_tag}
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

        <!-- ${GRAMINEDIR}/CI-Examples/grpc/cpp/ratls/README.md -->

    - python

        <!-- ${GRAMINEDIR}/CI-Examples/grpc/python/ratls/README.md -->
