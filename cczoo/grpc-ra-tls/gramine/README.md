# RA-TLS Enhanced gRPC based on Gramine-SGX

## How to Build

1. Build gramine-sgx-dev docker image

    Please review the following document

    - cczoo/common/docker/gramine/README.md

2. Build grpc-ratls-dev docker image

    Execute the following command to build this docker image

    ```
    base_image=gramine-sgx-dev:v1.2-ubuntu20.04-latest
    image_tag=grpc-ratls-dev:graminev1.2-ubuntu20.04-latest
    ./build_docker_image.sh ${base_image} ${image_tag}
    ```

    `gramine-sgx-dev:v1.2-ubuntu18.04-latest` and `gramine-sgx-dev:v1.2-ubuntu20.04-latest` 
    could be selected as base_image.

## How to run gRPC examples

1. start container

    ```
    cczoo/grpc-ra-tls/gramine/start_container.sh ${pccs_service_ip} ${image_tag}
    ```

2. Start aesm service

    ```
    /root/start_aesm_service.sh
    ```

3. build and run gRPC examples

    ```
    export SGX_RA_TLS_BACKEND=GRAMINE
    ```

    - c++

        ${GRAMINEDIR}/CI-Examples/grpc/cpp/ratls/README.md

    - python

        ${GRAMINEDIR}/CI-Examples/grpc/python/ratls/README.md
