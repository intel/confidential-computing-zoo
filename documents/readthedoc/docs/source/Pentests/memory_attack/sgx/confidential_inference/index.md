# Confidential Inference

## Introduction

In the traditional AI inference workflow, it usually faces security risks of models and user data.

Developers usually adopt model encryption and TLS network transmission methods to solve data security risks in AI inference workflow.

Although the above two security methods can solve the data security issues in the storage and transmission process, there are still data security risks in this workflow, and hackers can get model and user data through memory attacks.

In the following demo, we will conduct attack simulation and security verification to demonstrate the effectiveness and limitations of the above security methods, and use intel SGX technology to prevent data theft through memory attacks, so as to achieve all-round (model storage, data network transport, inference service runtime) to protect the purpose of AI inference workflow.

The participants of the AI inference workflow are divided into the following four roles: `Model Distributor`, `inf Server`, `inf Client` and `Hacker`.

![](confidential_inference.svg)

---

## Setup Environment

1. Build docker image

    ```
    image=confidential-inference:graminev1.2-ubuntu20.04-latest
    build_docker_image.sh ${image}
    ```

2. Start container

    ```
    ./start_container.sh ${image}
    ```

    It will create the following containers for the above 4 roles respectively:
    - `model-distributor` container for `Model Distributor`
    - `inf-client` container for `inf Client`
    - `inf-server` container for `inf Server`
    - `inf-server` container for `Hacker`

---

## Encrypt and Transfer Model

1. `Model Distributor` encrypt model in `model-distributor` container.

    Encryption algorithm:

    AES in CBC mode with a 128-bit key for encryption; using PKCS7 padding. HMAC using SHA256 for authentication.

    Encrypt model with password:

    ```
    python3 /models.py
    ```

    Get outputs:

    ```
    Save data to /resnet50.encrypt.pkl

    Weights data: [<tf.Variable 'conv1_conv/kernel:0' shape=(7, 7, 3, 64) dtype=float32, numpy=
    array([[[[ 2.82526277e-02, -1.18737184e-02,  1.51488732e-03, ...,
            -1.07003953e-02, -5.27982824e-02, -1.36667420e-03],
            [ 5.86827798e-03,  5.04415408e-02,  3.46324709e-03, ...,
            1.01423981e-02,  1.39493728e-02,  1.67549420e-02],
            [-2.44090753e-03, -4.86173332e-02,  2.69966386e-03, ...,
            -3.44439060e-04,  3.48098315e-02,  6.28910400e-03]],

            [[ 1.81872323e-02, -7.20698107e-03,  4.80302610e-03, ...,
            -7.43396254e-03, -8.56800564e-03,  1.16849300e-02],
            [ 1.87554304e-02,  5.12730293e-02,  4.50406177e-03, ...,
            1.39413681e-02,  1.26296384e-02, -1.73004344e-02],
            [ 1.90453827e-02, -3.87909152e-02,  4.25842637e-03, ...,
            2.75742816e-04, -1.27962548e-02, -8.35626759e-03]],

            [[ 1.58849321e-02, -1.06073255e-02,  1.30999666e-02, ...,
            -2.26797583e-03, -3.98984266e-04,  3.39989027e-04],
            [ 3.61421369e
    ```

2. Transfer model from `model-distributor` container to `inf-server` container.

   - `Model Distributor` in `model-distributor` container

        ```
        cp /resnet50.encrypt.pkl /home/host-home/
        ```

   - `inf Server` in `inf-server` container

        ```
        cp /home/host-home/resnet50.encrypt.pkl /
        ```

    - `Hacker` in `inf-server` container

        Hacker opens the encrypted model:

        ```
        head -c 500 /resnet50.encrypt.pkl
        ```

        Get outputs:

        ```
        gAAAAABjtpV6qk-XxaMNcCIrbC3Wo5eShJt9eRxWl4AV9duNn4aXHw8qB67ES2AcJwHCJTyTa2tL01DNnUUF2ummGF1fTj71WzEUA91au1bulEqqvkgLRKT_7DSkcB38PCC5EgviLTmuwq9LrjOE55G_XgRn7XOXru6Q72B_JF4SdcVG6XikwPt-ThIiKJGZVnZaIEqZ
        ```

---

## Network Attack and Memory Attack

1. `inf Server` setup HTTP/HTTPS Configure in `inf-server` container.

    - HTTP Protocol

        ```
        export CERT_PATH="none"
        export KEY_PATH="none"
        ```

    - HTTPS Protocol

        ```
        export CERT_PATH=/cert.pem
        export KEY_PATH=/key.pem

        SERVER_CN=infer.service.com
        openssl req -x509 -sha256 -nodes -days 365 -newkey rsa:2048 -out cert.pem -keyout key.pem -subj "/CN=${SERVER_CN}"
        ls *.pem

        cp cert.pem /home/host-home/
        ```

2. `inf Server` start AI inference server with password in `inf-server` container.

    ```
    taskset -c 1-7 python3 /server.py -host 0.0.0.0 -port 8091 -cert ${CERT_PATH} -key ${KEY_PATH}
    ```

    Get outpus:

    ```
    * Serving Flask app 'server'
    * Debug mode: off
    WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
    * Running on all addresses (0.0.0.0)
    * Running on http://127.0.0.1:8091
    * Running on http://172.18.0.7:8091
    ```

3. `Hacker` listen network in `inf-server` container.

    ```
    tcpdump --interface any -X 'tcp dst port 8091' -s 0 -A -w net_dump.pcap
    ```

4. `inf Client` sends the image in `inf-client` container.

    Configure:

    - HTTP Protocol

        ```
        export PROTOCOL=http
        export CERT_PATH="none"
        ```

    - HTTPS Protocol

        ```
        export PROTOCOL=https
        export CERT_PATH=/cert.pem

        cp /home/host-home/cert.pem .
        ```

    `inf Client` sends the image to `inf Server`:

    ```
    unset http_proxy https_proxy
    python3 ./client.py -host ${PROTOCOL}://infer.service.com:8091 -cert ${CERT_PATH} -image /dataset/goldfish.jfif
    ```

    Get outputs:

    ```
    Status: 200, Response: AI Inferernce Service
    Status: 200, Response: {"class":[["n01443537","goldfish","0.95790315"],["n02655020","puffer","0.027560642"],["n01440764","tench","0.0038917565"]]}

    image strings: AAAQQgAAVEIAAJJCAAAoQgAAXEIAAJRCAAAUQgAAREIAAHxCAAAUQgAAPEIAAGRCAAAIQgAALEIAAFBCAACgQQAA0EEAABhCAADAQQAA2EEAADhCAADAQQAA2EEAAChCAAC4QQAA6EEAACxCAADAQQ
    ```

5. `Hacker` parse dumped network data in `inf-server` container.

    ```
    strings net_dump.pcap | grep image= | cut -c 1-76
    ```

    - HTTP Protocol

        Get outputs:

        ```
        image=AAAQQgAAVEIAAJJCAAAoQgAAXEIAAJRCAAAUQgAAREIAAHxCAAAUQgAAPEIAAGRCAAAIQgAALEIAAFBCAACgQQAA0EEAABhCAADAQQAA2EEAADhCAADAQQAA2EEAAChCAAC4QQAA6EEAACxCAADAQQ
        ```

    - HTTPS Protocol

        Get none outputs. HTTPS/TLS can effectively protect the security of user data during network transmission.

6. `Hacker` dump memory in `inf-server` container.

    ```
    rm -rf core.*
    gdb -ex "generate-core-file" -ex "set confirm off" -ex "quit" -p `pgrep -f python`
    strings core.* > mem_dump_nosgx.log

    grep -n "AAAQQgAAVEIAAJJCAAAoQgAAXEIAAJRCAAAUQgAAREIAAHxCAAAUQgAAPE" mem_dump_nosgx.log | cut -c 1-70

    cat mem_dump_nosgx.log | tail -n +`grep -n 'shape=(7, 7, 3, 64) dtype=float32' mem_dump_nosgx.log | awk -F: '{print $1}'` | head -n 17
    ```

    The hacker gets the plain image and model:

    ```
    2033125:AAAQQgAAVEIAAJJCAAAoQgAAXEIAAJRCAAAUQgAAREIAAHxCAAAUQgAAPEIAAGRCAAAIQgAALEIAAFBCAACgQQAA0EEAABhCAADAQQAA2EEAADhCAADAQQAA2EEAAChCAAC4QQAA6EEAAC

    [<tf.Variable 'conv1_conv/kernel:0' shape=(7, 7, 3, 64) dtype=float32, numpy=
    array([[[[ 2.82526277e-02, -1.18737184e-02,  1.51488732e-03, ...,
            -1.07003953e-02, -5.27982824e-02, -1.36667420e-03],
            [ 5.86827798e-03,  5.04415408e-02,  3.46324709e-03, ...,
            1.01423981e-02,  1.39493728e-02,  1.67549420e-02],
            [-2.44090753e-03, -4.86173332e-02,  2.69966386e-03, ...,
            -3.44439060e-04,  3.48098315e-02,  6.28910400e-03]],
            [[ 1.81872323e-02, -7.20698107e-03,  4.80302610e-03, ...,
            -7.43396254e-03, -8.56800564e-03,  1.16849300e-02],
            [ 1.87554304e-02,  5.12730293e-02,  4.50406177e-03, ...,
            1.39413681e-02,  1.26296384e-02, -1.73004344e-02],
            [ 1.90453827e-02, -3.87909152e-02,  4.25842637e-03, ...,
            2.75742816e-04, -1.27962548e-02, -8.35626759e-03]],
            [[ 1.58849321e-02, -1.06073255e-02,  1.30999666e-02, ...,
            -2.26797583e-03, -3.98984266e-04,  3.39989027e-04],
            [ 3.61421369e-02,  5.02430499e-02,  1.22699486e-02, ...,
            1.19910473e-02,  2.02837810e-02, -1.96981970e-02],
    ```

---

## Confidential Inference with Gramine-SGX

1. `inf Server` start AI inference server in `inf-server` container.

    Start with HTTPS protocol:

    ```
    export CERT_PATH=/cert.pem
    export KEY_PATH=/key.pem

    make clean && make

    taskset -c 1-7 gramine-sgx python ./server.py -host 0.0.0.0 -port 8091 -cert ${CERT_PATH} -key ${KEY_PATH}
    ```

2. `inf Client` sends the image in `inf-client` container.

    ```
    export PROTOCOL=https
    export CERT_PATH=/cert.pem
    unset http_proxy https_proxy
    python3 ./client.py -host ${PROTOCOL}://infer.service.com:8091 -cert ${CERT_PATH} -image /dataset/goldfish.jfif
    ```

3. `Hacker` dump memory in `inf-server` container.

    ```
    rm -rf core.*
    gdb -ex "generate-core-file" -ex "set confirm off" -ex "quit" -p `pgrep -f python`
    strings core.* > mem_dump_sgx.log

    grep -n "AAAQQgAAVEIAAJJCAAAoQgAAXEIAAJRCAAAUQgAAREIAAHxCAAAUQgAAPE" mem_dump_sgx.log | cut -c 1-70

    cat mem_dump_sgx.log | tail -n +`grep -n 'shape=(7, 7, 3, 64) dtype=float32' mem_dump_sgx.log | awk -F: '{print $1}'` | head -n 17
    ```

    The hacker can not get the plain image and model. `Intel SGX` can effectively protect the memory safety of inference service runtime.

This confidential inference service protects the security of models and user data in an all-round way through model encrypted storage, data TLS network transmission and SGX protection of runtime memory.

