# GRPC-Gramine-SGX-Dev Image

## How to Build

1. Build gramine-sgx-dev docker image

    Please review the following document

    - cczoo/common/docker/gramine/README.md

2. Build grpc-gramine-sgx-dev docker image

    Execute the following command to build this docker image

    ```
    ./build_docker_image.sh
    ```

## How to run gRPC examples

1. start container

    ```
    cczoo/grpc-ra-tls/start_container.sh ${pccs_service_ip}
    ```

2. Start aesm service

    ```
    /root/start_aesm_service.sh
    ```

3. build and run gRPC examples

    c++

    - ${GRAMINEDIR}/CI-Examples/grpc/cpp/ratls/README.md

    python

    - ${GRAMINEDIR}/CI-Examples/grpc/python/ratls/README.md
