# Key Generator Application Memory Attack

## Introduction

This application is generating keys in memory and implemented based on the Intel SGX SDK.

It will use the same source code to compile SGX applications and non-SGX applications, and perform memory attacks on them to verify the confidentiality of SGX runtime memory.

![](key_generator.svg)

## Application Deployment

1. Install Intel(R) Software Guard Extensions (Intel(R) SGX) SDK for Linux* OS.

2. Make sure your environment is set:
    ```
    source ${sgx-sdk-install-path}/environment
    ```

3. Build application:

    - Without Intel SGX Memory Protection
        ```
        make clean
        make SGX_MODE=SIM SGX_DEBUG=0
        ```

    - With Intel SGX Memory Protection
        ```
        make clean
        make SGX_DEBUG=0
        ```

4. Execute the binary directly:

    ```
    ./app
    ```

## Hacker Memory Attack

1. Dump app's memory via gdb:
    ```
    rm -rf core.*
    gdb -ex "generate-core-file" -ex "quit" -p `pgrep -f app`
    ```

2. Parse and find key in dumped file:
    ```
    strings ./core.* | grep -n Secret_Key
    ```

    Corresponding output:

    - Without Intel SGX Memory Protection
        ```
        1233:Secret_Key:uLhtfhrxoxTPwQdquZTtKhJcigdJTrHzJTaKBewwwiGhGuEXqNnjuRTfnapTMTAwWJsKMIveISmIVmllxCxHsjPHldjadgqIrreXAwkxMHRCwcOLchYpjKrRlyZIVDAp
        ```
    - Intel SGX Memory Protection

        None output.