# Encrypted VFS and TDX-RA Enhanced Tensorflow Serving

This solution presents a security enhanced TensorFlow Serving framework to guarantee security during transmission (TLS), runtime ([Intel® TDX (Trust Domain Extensions)](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-trust-domain-extensions.html)) and storage ([Encrypted VFS](https://github.com/intel/confidential-computing-zoo/tree/main/cczoo/tdx-encrypted-vfs)).


## Introduction

TensorFlow Serving is a Google open source project. It is a flexible high-performance machine learning model serving system. Its main function is to load and run models trained by TensorFlow, provide external access interfaces, and provide online reasoning services.

Intel® TDX is a CPU hardware-based isolation and encryption technology that provides runtime data security (such as CPU registers, memory data, and interrupt injection) for services within a TDX VM instance. Intel® TDX provides default out-of-the-box protection for your instances and applications. You can migrate existing applications to TDX instances to secure them without modifying application code.

In addition to runtime security, the encrypted VFS provides data storage security for services, preventing model and certificate theft.

This practice provides a reference implementation for developers to use cloud servers based on Intel® TDX technology. Through this article, you can obtain the following information:

- Have an overall understanding of the end-to-end full data lifecycle security solution based on TDX technology.

- Provides a feasible reference framework and scripts for developers using the security-enhanced cloud TDX server.

## Architecture

![](tf-serving.svg)

This practice involves three roles: Trusted side, Untrusted cloud side, and Client side.

- Trusted Side

    The client uses the LUKS (Linux Unified Key Setup) toolkit to create encrypted file blocks, encrypt and store the trained models into the file block, and upload these models to the cloud TDX environment in the form of encrypted file blocks. At the same time, the client will also deploy key management services, which are mainly used for remote authentication of the cloud TDX environment to ensure the credibility of the cloud TDX environment; after the verification is passed, the key will be sent to the cloud through TLS encrypted transmission Encrypted file block mount service in TDX.

- Untrusted Cloud Side

    Deployed in cloud server, providing TDX confidential computing environment, encrypted file blocks and TensorFlow Serving reasoning service run in this environment. When mounting an encrypted file block, a key request will be sent to the client. After the client verifies the authenticity of the current TDX environment through remote authentication, the client will send the key to the cloud to decrypt and mount the file block. TensorFlow Serving will access the model in the path after the file block is mounted and deploy it.

- Client Side

    Third-party users send data to the inference service running in the TDX confidential computing environment through secure transmission over the TLS network. After the reasoning is completed, the returned result is obtained.

``Note:``In order to facilitate the deployment and testing of developers, this practice deploys the above three roles in the same cloud instance.

## Deployment

### Trusted Side

1. Prepare source code

    ```
    git clone https://github.com/intel/confidential-computing-zoo.git
    cd confidential-computing-zoo/cczoo/tdx-tf-serving-ppml
    cp -r ../tdx-encrypted-vfs ./tools
    ```

2. Create encrypted VFS with block device

    ```
    apt-get install -y cryptsetup

    FS_DIR=luks_fs
    ./tools/create_encrypted_vfs.sh ${FS_DIR}
    ```

    After above, user need to create env `LOOP_DEVICE` to bind to the loop device manually.

    ```
    export LOOP_DEVICE=<the binded loop device in outputs>
    ```

3. Mount and format block device

    The encryption key needs to be entered manually during the mount process.

    ```
    ./tools/mount_encrypted_vfs.sh ${LOOP_DEVICE} luks_fs format
    ```

4. Download and convert model

    ```
    cd server/scripts

    pip3 install pip --upgrade
    pip3 install -r requirements.txt

    ./download_model.sh

    python3 -u model_graph_to_saved_model.py --import_path model/resnet50-v15-fp32/resnet50-v15-fp32.pb --export_dir model/resnet50-v15-fp32
    ```

5. Generate server SSL/TLS certificate and configure

    Create a TLS certificate for TensorFlow Serving for encrypted communication with the remote client.

    ```
    service_domain_name=grpc.tf.service.com
    ./generate_ssl_config.sh ${service_domain_name}
    ```

6. Copy model and certificate to encrypted block device

    ```
    cp -r model ssl_configure /mnt/${FS_DIR}
    cd -
    ```

7. Build TensorFlow Serving docker image

    ```
    server/docker/build_docker_image.sh
    ```

8. Compile and deploy the get secret service

    Compile service:

    ```
    cd ./tools/get_secret
    source ./tdx_env
    ./build_grpc_get_secret.sh

    cp ${GRPC_PATH}/examples/cpp/secretmanger/build/client .
    cp ${GRPC_PATH}/examples/cpp/secretmanger/build/server .
    cp ${GRPC_PATH}/examples/cpp/secretmanger/build/*.json .
    ```

    Configure key: The key is saved in `secret.json` in the form of `{<key>:<password>}`, where the key is set to `{"tdx":<password>}`.

    Deployment `get_secret` service:

    ```
    export hostname=localhost:50051
    ./server -host=${hostname} &
    cd -
    ```

### Untrusted Cloud Side

1. Mount encrypted file block device

    Unmount the previously mounted block device, get the key via remote attestation, and mount it again.

    ```
    ./tools/unmount_encrypted_vfs.sh /root/vfs luks_fs
    ./tools/mount_encrypted_vfs.sh ${LOOP_DEVICE} luks_fs notformat get_secret
    ```

2. Deploy tensorflow serving service

    ```
    server/docker/start_tf_serving_container.sh -v /mnt/${FS_DIR} -m resnet50-v15-fp32
    ```

### Client Side

1. Setup environment

    ```
    service_ip=127.0.0.1
    echo "${service_ip} ${service_domain_name}" >> /etc/hosts

    pip3 install pip --upgrade
    pip3 install -r client/requirements.txt

    # for ubuntu
    apt-get install -y libgl1-mesa-glx
    # for centos
    yum install mesa-libGL
    ```

2. Remote inference via TLS

    The inference result will be printed in the terminal.

    ```
    python3 -u client/resnet_client_grpc.py --url ${service_domain_name}:8500 --crt server/scripts/ssl_configure/server.crt --batch 1 --cnum 1 --loop 50
    ```

    Inference result:

    ```
    query: secure channel, task 0, batch 1, loop_idx 0, latency(ms) 375.7, tps: 2.7
    query: secure channel, task 0, batch 1, loop_idx 1, latency(ms) 87.4, tps: 11.4
    query: secure channel, task 0, batch 1, loop_idx 2, latency(ms) 86.6, tps: 11.5
    query: secure channel, task 0, batch 1, loop_idx 3, latency(ms) 86.0, tps: 11.6
    query: secure channel, task 0, batch 1, loop_idx 4, latency(ms) 85.4, tps: 11.7

    ...

    summary: cnum 1, batch 1, e2e time(s) 0.7239549160003662, average latency(ms) 144.24099922180176, tps: 6.9065074212404
    ```

## Cloud Practice

1. Aliyun ECS

    Aliyun ECS (Elastic Compute Service) is an IaaS (Infrastructure as a Service) level cloud computing service provided by Alibaba Cloud. It builds eighth generation security-enhanced instance families based on Intel® TDX technology to provide a trusted and confidential environment with a higher security level.

    About how to build TDX confidential computing instance, please refer to the below links:

    Chinese version: https://www.alibabacloud.com/help/zh/elastic-compute-service/latest/build-a-tdx-confidential-computing-environment

    English version：https://www.alibabacloud.com/help/en/elastic-compute-service/latest/build-a-tdx-confidential-computing-environment

    Notice: Ali TDX instance is under external public preview.
