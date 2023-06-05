# Horizontal Federated Learning with Intel TDX Confidential Containers

This solution presents a framework for developing a PPML(Privacy-Preserving Machine Learning) solution based on TensorFlow - Horizontal Federated Learning with [CoCo (Confidential Containers)](https://github.com/confidential-containers/operator) - Intel TDX.

## Introduction

How to ensure the privacy of participants in the distributed training process of deep neural networks is a current hot topic. Federated learning can solve the problem to a certain extent. In horizontal federated learning, each participant uses its own local data for algorithm iteration and only uploads gradient information instead of raw data, which guarantees data privacy to a large extent.

The commonly used encryption method in federated learning is Homomorphic Encryption(HE). In addition to HE, trusted execution environment (TEE) technology uses plaintext for calculation and uses a trusted computing base to ensure security. Intel TDX technology is a concrete realization of TEE technology. In this horizontal federated learning solution, we adopted a privacy protection computing solution based on Intel TDX technology.

This solution mainly include the following two aspects:

- Federated training

    Propose a federated training reference solution based on privacy protection technology.

- Privacy protection

    Using some privacy protection technology to protect the security of FL, such as storage of docker image, runtime of FL training, distributed communication and storage of model in cloud environment.

## Privacy protection

In this solution, privacy protection is provided in the following aspects:

- Docker image and runtime security

    In the training phase of federated learning, the gradient information is stored inside the Intel® TDX Confidential Containers.

    The Intel® TDX Confidential Containers is for protecting confidentiality and integrity of sensitive workload and data running in cloud native way using container and Kubernets by leveraging Intel® Trust Domain Extensions (TDX), Encrypt-Cosign-RA docker image technology.

    Intel® TDX protect confidential guest VMs from the host and physical attacks by isolating the guest register state and by encrypting the guest memory. For more details please visit [Intel® TDX White Papers & Specs](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-trust-domain-extensions.html).

    Encrypt-Cosign-RA technology combines the encryption, signature and remote attestation process of the docker image, which simplifies the workflow and ensures the security of the docker image on the cloud.

- Distributed communication security

    We use the Remote Attestation with Transport Layer Security (RA-TLS) of Intel TDX technology to ensure security during transmission.

    This technology combines TLS technology and remote attestation technology. RA-TLS uses TEE as the hardware root of trust. The certificate and private key are generated in the TD and are not stored on the disk. Therefore, participants cannot obtain the certificate and private key in plain text, preventing the man-in-the-middle attacks. In this federated learning solution, RA-TLS is used to ensure the encrypted transmission of gradient information.

    For more information about RA-TLS, please refer to the relevant [documentation](https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html)and [code](https://github.com/intel/confidential-computing-zoo/tree/main/cczoo/grpc-ra-tls).

- Model at-rest security

    We use the LUKS storage service to encrypt the model generated during the training process, to protect the model from being acquired by malicious hosts and only visible in the TD.

    Therefore, safe storage of the model is achieved. In addition, we use the Trusted machine with LUKS Secrets to obtain the model in TD through RA-TLS technology. Therefore, the safe migration of the model is achieved.

## Workflow

In the training process, each worker uses local data in its TD to complete a round of training, and then sends the gradient information in the backpropagation process to the parameter server through the RA-TLS technology, and then the parameter server completes the gradient aggregation and update network parameters, and then send the updated parameters to each worker. The workflow is as follows:

![](images/hfl-tdx-coco.svg)

The training phase can be divided into the following steps:

&emsp;&ensp;**①** Using TDX CoCo technology, the training program of the participants runs in different TDs (Trusted domain, TDX container in CoCo VM). Create encrypted model directory on LUKS storage system and prepare LUKS decryption service.

&emsp;&ensp;**②** Workers calculate gradient information based on local data in the TD.

&emsp;&ensp;**③** Workers send gradient to parameter server through RA-TLS enhanced gRPC.

&emsp;&ensp;**④** Parameter server performs gradient aggregation and updates global model parameters.

&emsp;&ensp;**⑤** Parameter server sends model parameters to workers.

&emsp;&ensp;**⑥** Workers update local model parameters.

&emsp;&ensp;**⑦** Repeat steps **②**-**⑥** until the end of training. Finally, the training model directory is transmitted to the remote trusted node and finally decrypted.

## TDX CoCo stack deployment

1. Install CoCo

    Please refer to CoCo [doc](https://github.com/confidential-containers/operator/blob/main/docs/INSTALL.md) for detail.

2. Enable kubernetes's flannel and ingress

    ```shell
    git clone https://github.com/intel/confidential-computing-zoo.git
    cczoo_dir=`pwd -P`/confidential-computing-zoo/cczoo
    hfl_coco_dir=$cczoo_dir/horizontal_fl_coco

    kubectl apply -f $hfl_coco_dir/k8s/flannel/deploy.yaml
    kubectl apply -f $hfl_coco_dir/k8s/ingress-nginx/deploy.yaml
    kubectl delete -A ValidatingWebhookConfiguration ingress-nginx-admission
    ```

3. Setup CoCo registry

    deploy:

    ```shell
    cd $hfl_coco_dir/k8s/registry
    ./deploy_self_hosted_registry.sh -i k8s

    cd $hfl_coco_dir/coco_tools/scripts
    ./update_guest_rootfs.sh append_certificate

    registry_address=registry.domain.local
    no_proxy=$no_proxy,$registry_address
    echo $no_proxy >> /etc/hosts
    ```

    test:

    ```shell
    curl --noproxy '*' https://$registry_address/v2/_catalog
    ```

4. Add hosts to kubernetes's CoreDNS

    Replace <XXX_ADDRESS> to the corresponding address.

    ```shell
    kubectl edit configmap -n kube-system coredns

        ...

        kubernetes cluster.local in-addr.arpa ip6.arpa {
           pods insecure
           fallthrough in-addr.arpa ip6.arpa
           ttl 30
        }
        hosts {
           <PCCS_ADDRESS> pccs.service.com
           <SECRET_RA_ADDRESS> ra.service.com
           <REGISTRY_ADDRESS> registry.domain.local
           <INGRESS_ADDRESS> ps0.hfl-tdx-coco.service.com
           <INGRESS_ADDRESS> w0.hfl-tdx-coco.service.com
           <INGRESS_ADDRESS> w1.hfl-tdx-coco.service.com
           fallthrough
        }
        prometheus :9153
        forward . /etc/resolv.conf {
           max_concurrent 1000
        }

        ...
    ```

5. Setup verdictd(optional)

    ```shell
    cd $hfl_coco_dir/coco_tools/verdictd

    cat << EOF | tee ./opt/verdictd/keys/84688df7-2c0c-40fa-956b-29d8e74d16c0
    1234567890123456789012345678901
    EOF

    docker build -t verdictd:v1 \
        --build-arg http_proxy="${http_proxy}" \
        --build-arg https_proxy="${https_proxy}" \
        .

    docker run -d \
        --restart=always \
        --name verdictd \
        --network host \
        -v "$(pwd)"/opt/verdictd:/opt/verdictd \
        verdictd:v1

    docker logs verdictd
        [2023-02-27T02:47:15Z INFO  verdictd] Verdictd info: v0.0.1
            commit: 1d632bebe5546ef300beba8eb6c2cf32fb266d55
            buildtime: 2023-02-26 05:42:40 +00:00
        [2023-02-27T02:47:15Z INFO  verdictd] Listen client API server addr: 127.0.0.1:50001
        [2023-02-27T02:47:15Z INFO  verdictd] Listen addr: 0.0.0.0:50000
    ```

6. Setup skopeo(optional)

    Please refer to [skopeo](https://github.com/containers/skopeo/blob/main/install.md) to install it.

    ```shell
    # Create skopeo policy file
    mkdir -p /etc/containers/
    cat << EOF | tee "/etc/containers/policy.json"
    {
        "default": [
            {
                "type": "insecureAcceptAnything"
            }
        ],
        "transports":
            {
                "docker-daemon":
                    {
                        "": [{"type":"insecureAcceptAnything"}]
                    }
            }
    }
    EOF

    # Generate the key provider configuration file for skopeo
    mkdir -p /etc/containerd/ocicrypt/
    cat <<EOF | tee "/etc/containerd/ocicrypt/ocicrypt_keyprovider.conf"
    {
            "key-providers": {
                    "attestation-agent": {
                        "grpc": "127.0.0.1:50001"
                    }
            }
    }
    EOF
    ```

7. Setup cosign(optional)

    ```shell
    wget https://github.com/sigstore/cosign/releases/download/v2.0.0/cosign-linux-amd64
    install -D --owner root --group root --mode 0755 cosign-linux-amd64 /usr/local/bin/cosign

    cd $hfl_coco_dir/coco_tools/verdictd
    cat <<EOF > ./opt/verdictd/image/policy.json
    {
        "default": [
            {
                "type": "reject"
            }
        ],
        "transports": {
            "docker": {
                "registry.domain.local": [
                    {
                        "type": "sigstoreSigned",
                        "keyPath": "/run/image-security/cosign/cosign.pub"
                    }
                ]
            }
        }
    }
    EOF
    ```

8. Setup guest kernel params of CoCo

    check `kernel_params`:

    ```shell
    cat /opt/confidential-containers/share/defaults/kata-containers/configuration-qemu-tdx.toml | grep -n kernel_params

        tdx_disable_filter debug_console_enabled=true agent.enable_signature_verification=false  cc_rootfs_verity.scheme=dm-verity cc_rootfs_verity.hash=08fe47ace98d55a7aa59a82d1cf3da51b9b507ad93bbaf70786c41d49e2cefee
    ```

    Replace `kernel_params` with following params:

    ```shell
    kernel_params = "tdx_disable_filter debug_console_enabled=true cc_rootfs_verity.scheme=none cc_rootfs_verity.hash=<ROOTFS_HASH> 
    agent.http_proxy=<PROXY_ADDRESS> agent.https_proxy=<PROXY_ADDRESS> agent.no_proxy=localhost,127.0.0.1,registry.domain.local agent.enable_signature_verification=false agent.aa_kbc_params=eaa_kbc::<VERDICTD_ADDRESS>:50000"
    ```

    Note:
    - <XXX_ADDRESS> is the corresponding ip address
    - Verify the guest rootfs(optional)
        - cc_rootfs_verity.scheme
        - cc_rootfs_verity.hash
    - Decrypt the encrypted docker image(optional)
        - agent.aa_kbc_params
    - Verify the signature of docker image(optional)
        - agent.enable_signature_verification

9. Setup guest resource of CoCo

    ```shell
    $hfl_coco_dir/coco_tools/scripts/update_guest_rootfs.sh set_default_vcpu_memory --vcpu=4 --memory=32768
    $hfl_coco_dir/coco_tools/scripts/update_guest_rootfs.sh update_image_storage_size --size=20G
    ```

## Horizontal federated learning deployment

### Configuration

- framework: TensorFlow 2.6.0
- model: ResNet-50
- dataset: Cifar-10
- ps num: 1
- worker num: 2
- container num: 3

### Deployment

1. Prepare encrypted partition for model

    Need to input password to create encrypted partition.

    ```shell
    cd $hfl_coco_dir/luks_tools

    VFS_SIZE=1G
    VFS_PATH=`pwd -P`/vfs
    ./create_encrypted_vfs.sh $VFS_PATH $VFS_SIZE
    ```

2. Prepare secretmanger service and runtime

    This service aims to provide password for remote encrypted vfs.
    <SECRET_MANAGER_ADDRESS> is ip of secretmanger service.

    ```shell
    cczoo_path=/tmp/confidential-computing-zoo
    encrypted_vfs_path=$cczoo_path/cczoo/tdx-encrypted-vfs

    git clone https://github.com/intel/confidential-computing-zoo.git $cczoo_path
    cd $encrypted_vfs_path/get_secret
    git checkout 08f30d8bc616d60920f826ee8c633ff2d46a3c3b

    ./build_docker_image.sh
    ./start_container.sh <PCCS_ADDRESS>
    ./prepare_runtime.sh
    cp -r runtime $hfl_coco_dir/luks_tools
    ```

    Then add your `<APP_ID>:<PASSWORD>` to `secret.json` in secretmanger container. <APP_ID> has been fixed to `hfl-tdx-coco-app`.

    ```
    docker exec -it secretmanger bash
        vim build/secret.json
            {
                <APP_ID>:<PASSWORD>,
                ...
            }
    docker restart secretmanger
    ```

3. Build docker image

    ```shell
    cd $hfl_coco_dir
    base_image=centos:8
    image=horizontal_fl:tdx-latest
    ./build_docker_image.sh $base_image $image
    ```

    ***Notice:***
    If you are using non-production version Intel CPU, please replace the `/usr/lib64/libsgx_dcap_quoteverify.so` file with non-production version.

4. Push docker image to CoCo registry

    ```shell
    docker tag $image $registry_address/$image
    docker push $registry_address/$image
    ```

5. Encrypt and cosign docker image(optional)

   - Encrypt docker image

       ```shell
       export OCICRYPT_KEYPROVIDER_CONFIG=/etc/containerd/ocicrypt/ocicrypt_keyprovider.conf
       skopeo copy --encryption-key provider:attestation-agent:84688df7-2c0c-40fa-956b-29d8e74d16c0 docker://$registry_address/$image docker://$registry_address/horizontal_fl:tdx-encrypt-latest
       ```

   - Cosign docker image

       ```shell
       # Generate a new key pair
       cd $registry_address/tools/verdictd
       cosign generate-key-pair

       # Enable cosign image signature verification with verdictd
       cp cosign.pub $hfl_coco_dir/coco_tools/opt/verdictd/image/cosign.key
       docker restart verdictd

       # sign docker image
       cosign sign --key cosign.key $registry_address/horizontal_fl:tdx-encrypt-latest

       # Verify a signature on the supplied container image
       cosign verify --key cosign.pub $registry_address/horizontal_fl:tdx-encrypt-latest
       ```

   - Push docker image

       ```shell
       skopeo copy docker://$registry_address/horizontal_fl:tdx-encrypt-latest docker://$registry_address/horizontal_fl:tdx-encrypt-cosign-latest
       ```

6. Start the training with CoCo

    - Not encrypt and cosign docker image:

        ```shell
        kubectl apply -f $hfl_coco_dir/k8s/hfl-tdx-coco/ps/ps0.yaml
        kubectl apply -f $hfl_coco_dir/k8s/hfl-tdx-coco/ps/worker0.yaml
        kubectl apply -f $hfl_coco_dir/k8s/hfl-tdx-coco/ps/worker1.yaml
        ```

    - Encrypted and cosigned docker image:

        ```shell
        kubectl apply -f $hfl_coco_dir/k8s/hfl-tdx-coco-encrypt-cosign/ps/ps0.yaml
        kubectl apply -f $hfl_coco_dir/k8s/hfl-tdx-coco-encrypt-cosign/ps/worker0.yaml
        kubectl apply -f $hfl_coco_dir/k8s/hfl-tdx-coco-encrypt-cosign/ps/worker1.yaml
        ```

        You can see the training log information from the workers' pod to confirm that the training is running normally.

        ```shell
        kubectl exec -n hfl-tdx-coco -it service/hfl-tdx-coco-w0-service -- cat /hfl-tensorflow/worker0-python.log

            ...
            Info: tdx_qv_get_quote_supplemental_data_size successfully returned.
            Info: App: tdx_qv_verify_quote successfully returned.
            Info: App: Verification completed successfully.
            ...
            step: 0, loss: 2.676461, iter time: 7.650
            step: 1, loss: 2.566677, iter time: 2.679
            ...
            step: 7799, loss: 0.729082, iter time: 0.709
            Optimization finished.
        ```

        At the beginning of training, two-by-two remote verification between nodes will be performed. Only after the remote verification is passed can the training continue. After successful remote attestation, the terminal will output the following:

        ```shell
        Info: tdx_qv_get_quote_supplemental_data_size successfully returned.
        Info: App: tdx_qv_verify_quote successfully returned.
        Info: App: Verification completed successfully.
        ```

        The model files generated during training will be saved in the `model` folder. In this example, the information related to variable values is stored in `model/model.ckpt-data` of `ps0`, and the information related to the computational graph structure is stored in `model/model.ckpt-meta` of `worker0`.

7. Get model files from k8s pod

    Your can find the LUKS encrypted partition (`/luks_tools/vfs`) in k8s pod.

    ```shell
    kubectl exec -n hfl-tdx-coco -it service/hfl-tdx-coco-w0-service -- bash

    MOUNT_PATH=${WORKDIR}/model
    VFS_PATH=/luks_tools/vfs
    ls $MOUNT_PATH $VFS_PATH
    ```

    After transferring the LUKS encrypted partition (`/luks_tools/vfs`) to the customer's trusted environment, decrypt it in the trusted node and obtain the model file.

    If the path of the encrypted partition in the trusted node is `/luks_tools/vfs`, the command to decrypt and obtain the model file is as follows:

    ```shell
    cd luks_tools
    VFS_PATH=/luks_tools/vfs
    MOUNT_PATH=/luks_tools/model
    ./mount_encrypted_vfs.sh ${VFS_PATH} ${MOUNT_PATH}
    ```

    Finally, the decrypted model file is obtained on the trusted node:

    ```shell
    ls $MOUNT_PATH
    ```
