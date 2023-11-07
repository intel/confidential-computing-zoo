# Horizontal Federated Learning with Intel TDX

This solution presents a framework for developing a PPML (Privacy-Preserving Machine Learning) solution based on TensorFlow - Horizontal Federated Learning with Intel TDX.

## Introduction

How to ensure the privacy of participants in the distributed training process of deep neural networks is a current hot topic. Federated learning can solve the problem to a certain extent. In horizontal federated learning, each participant uses its own local data for algorithm iteration and only uploads gradient information instead of raw data, which guarantees data privacy to a considerable extent.

The commonly used encryption method in federated learning is Homomorphic Encryption(HE). In addition to HE, trusted execution environment (TEE) technology uses plaintext for calculation and uses a trusted computing base to ensure security. Intel TDX technology is a concrete realization of TEE technology. In this horizontal federated learning solution, we adopted a privacy protection computing solution based on Intel TDX technology.

This solution includes the following three aspects: 
-	RA-TLS enhanced gRPC - The RA-TLS technology is integrated in the gRPC framework to ensure the security of data transmission and enable remote verification technology.
-	Federated training – Propose a federated training solution based on Intel TDX and RA-TLS technology.
-	Model Protection – Using LUKS to protect model confidentiality and integrity during model training and model transfer. 

## Privacy Protection
In this solution, privacy protection is provided in the following aspects:

### Runtime Security Using Intel TDX
Intel TDX technology offers hardware-based memory encryption that isolates specific application code and data in memory. Intel TDX allows user-level code to allocate private regions of memory based on a TD (Trust Domain) environment.

Intel TDX also helps protect against SW attacks even if OS/drivers/BIOS/VMM/SMM are compromised and helps increase protections for secrets even when attacker has full control of platform.

In the training phase of federated learning, the gradient information is stored inside the TD. Intel TDX provides assurance that no unauthorized access or memory snooping of the TD occurs to prevent leakage of gradient and model information.

### Encrypted Transmission with Remote Attestation
We use the Remote Attestation with Transport Layer Security (RA-TLS) of Intel TDX technology to ensure security during transmission. This technology combines TLS technology and remote attestation technology. RA-TLS uses TEE as the hardware root of trust. The certificate and private key are generated in the TD and are not stored on the disk. Therefore, participants cannot obtain the certificate and private key in plain text, preventing the man-in-the-middle attacks. In this federated learning solution, RA-TLS is used to ensure the encrypted transmission of gradient information.

For more information about RA-TLS, please refer to the relevant [documentation](https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html) and [code](https://github.com/intel/confidential-computing-zoo/tree/main/cczoo/grpc-ra-tls).

### Model At-Rest Security 
We use the LUKS storage service to encrypt the model generated during the training process, to protect the model from being acquired by malicious hosts and only visible in the TD. Therefore, safe storage of the model is achieved. In addition, we use the Trusted machine with LUKS Secrets to obtain the model in TD through RA-TLS technology. Therefore, the safe migration of the model is achieved.

## Workflow
In the training process, each worker uses local data in its TD to complete a round of training, and then sends the gradient information in the backpropagation process to the parameter server through the RA-TLS technology, and then the parameter server completes the gradient aggregation and update network parameters, and then send the updated parameters to each worker. The workflow is as follows:

![](images/tdx_hfl.svg)

The training phase can be divided into the following steps:

&emsp;&ensp;**①** Using Intel TDX technology, the training program of the participants runs in different TDs. Create encrypted model directory on LUKS storage system and prepare LUKS decryption service.

&emsp;&ensp;**②** Workers calculate gradient information based on local data in the TD.

&emsp;&ensp;**③** Workers send gradient to parameter server through RA-TLS enhanced gRPC.

&emsp;&ensp;**④** Parameter server performs gradient aggregation and updates global model parameters.

&emsp;&ensp;**⑤** Parameter server sends model parameters to workers.

&emsp;&ensp;**⑥** Workers update local model parameters.

&emsp;&ensp;**⑦** Repeat steps **②**-**⑥** until the end of training. Finally, the training model directory is transmitted to the remote trusted node and finally decrypted.

## Horizontal Federated Training Execution
This reference solution trains the ResNet-50 image classification model using the CIFAR-10 dataset.

### Prerequisites
- Intel TDX capable systems/VMs
- Docker Engine. Docker Engine is an open-source containerization technology for building and containerizing your applications.
  Please follow this [guide](https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script)
  to install Docker engine. It is recommended to use a data disk of at least 128GB for the docker daemon data directory. This [guide](https://docs.docker.com/config/daemon/#daemon-data-directory) describes how to configure the docker daemon data directory. If behind a proxy server, please refer to this [guide](https://docs.docker.com/config/daemon/systemd/) for configuring the docker daemon proxy settings.

- CCZoo source downloaded to each TD VM:
```
   git clone https://github.com/intel/confidential-computing-zoo.git
   cczoo_base_dir=$PWD/confidential-computing-zoo
```

### Configuration

- Framework: TensorFlow 2.6.0
- Model: ResNet-50
- Dataset: CIFAR-10
- Parameter Server num: 1
- Worker num: 2
- Total containers: 3

### Build and Start Containers
Build the container image on the TD VM(s). Alternatively, the container image can be built on any system and then transferred to the TD VMs.
#### Azure Deployments
For Azure deployments:

```shell
cd ${cczoo_base_dir}/cczoo/horizontal_fl_tdx
./build_docker_image.sh azure
```

NOTE: To specify the proxy server, set the `proxy_server` variable prior to the call to build_docker_image.sh, for example:
      
```
proxy_server=http://proxyserver:port ./build_docker_image.sh azure
```

Start three containers (ps0, worker0, worker1). Replace `<role>` with the role of the container (either `ps0`, `worker0`, or `worker1`). Replace `<image_id>` with the image ID of the container built from the previous step.

```shell
cd ${cczoo_base_dir}/cczoo/horizontal_fl_tdx
./start_container.azure.sh <role> <image_id>
```

#### Default Cloud Deployments
For cloud deployments other than on Azure:

```shell
cd ${cczoo_base_dir}/cczoo/horizontal_fl_tdx
./build_docker_image.sh default
```

NOTE: To specify the proxy server, set the `proxy_server` variable prior to the call to build_docker_image.sh, for example:
      
```
proxy_server=http://proxyserver:port ./build_docker_image.sh
```

***Notice:*** 
If you are using non-production version Intel CPU, please modify the Dockerfile to replace `/usr/lib64/libsgx_dcap_quoteverify.so` with the non-production version.

Start three containers (ps0, worker0, worker1). Replace `<role>` with the role of the container (either `ps0`, `worker0`, or `worker1`). Replace `<image_id>` with the image ID of the container built from the previous step.

```shell
cd ${cczoo_base_dir}/cczoo/horizontal_fl_tdx
./start_container.sh <role> <image_id>
```

### Configure Node Network Addresses
If running in an environment with distributed nodes (for example, each container running on a separate VM), configure the node IP addresses by modifying the `/hfl-tensorflow/train.py` in each container:

```shell
tf.app.flags.DEFINE_string("ps_hosts", "['localhost:60002']", "ps hosts")
tf.app.flags.DEFINE_string("worker_hosts", "['localhost:61002','localhost:61003']", "worker hosts")
```

***Notice:***

1. You need to modify the `localhost` fields in the above code segment to the IP address of the VMs where the training script is deployed.
2. Make sure that the port number configured on the current node has been enabled on the corresponding VM.

### Configure Attestation Parameters
From each container configure attestation parameters.

#### Azure Deployments
From each container, modify `/etc/azure_tdx_config.json` to configure the attestation verifier service parameters.

To use [Intel Trust Authority](https://www.intel.com/content/www/us/en/security/trust-authority.html), modify `/etc/azure_tdx_config.json` as follows, specifying your Intel Trust Authority API key: `"api_key": "your project amber api key"`:

```bash
{
  "attestation_url": "https://api.projectamber.intel.com/appraisal/v1/attest",
  "attestation_provider": "amber",
  "api_key": "your project amber api key"
}
```

To use [Microsoft Azure Attestation](https://azure.microsoft.com/en-us/products/azure-attestation), modify `/etc/azure_tdx_config.json` as follows (an API key is not required):

```bash
{
  "attestation_url": "https://sharedeus2e.eus2e.attest.azure.net/attest/TdxVm?api-version=2023-04-01-preview",
  "attestation_provider": "maa",
  "api_key": ""
}
```

#### Default Cloud Deployments
For other cloud deployments, in all three containers, modify the `PCCS server address` in the `sgx_default_qcnl.conf` file and fill in the PCCS address of the cloud and ignore the `<PCCS ip addr>` parameter.

### Create Encrypted Storage
For each container, create encrypted storage to store the model files. When prompted for confirmation, type `YES` (in all uppercase). Enter a passphrase when prompted. Take note of the loop device output by `create_encrypted_vfs.sh`.

```shell
cd /luks_tools
export VIRTUAL_FS=/root/vfs
./create_encrypted_vfs.sh ${VIRTUAL_FS}
```

Replace `<loop device>` with the loop device output by `create_encrypted_vfs.sh` (`\dev\loop0` for example).
Replace `<role>` with the role of the container (either `ps0`, `worker0`, or `worker1`).
```shell
export LOOP_DEVICE=<loop device>
export ROLE=<role>
```

Format block device to ext4. Enter the passphrase when prompted.

```shell
./mount_encrypted_vfs.sh ${LOOP_DEVICE} format ${ROLE}
```

Mount encrypted storage.  Enter the passphrase when prompted.

```shell
./unmount_encrypted_vfs.sh ${ROLE}
./mount_encrypted_vfs.sh ${LOOP_DEVICE} noformat ${ROLE}
```

### Run Training Scripts
Run the training script from each container.

From the parameter server container:

```shell
cd /hfl-tensorflow
./test-tdx.sh ps0
```

From the worker0 container:

```shell
cd /hfl-tensorflow
./test-tdx.sh worker0
```

From the worker1 container:

```shell
cd /hfl-tensorflow
./test-tdx.sh worker1
```

You can see the training log information from the workers' terminals to confirm that the training is running normally.

At the beginning of training, remote attestation between the nodes will be performed. Only after the remote attestation succeeds can the training begin. After successful remote attestation, the terminal will output the following:

```shell
Info: App: Verification completed successfully.
```

The model files generated during training will be saved in the `model` folder. In this example, the information related to variable values is stored in `model/model.ckpt-data` of `ps0`, and the information related to the computational graph structure is stored in `model/model.ckpt-meta` of `worker0`.

Training is completed when both worker containers display the following output: `Optimization finished.`

After training is complete, unmount the storage on each container. Replace `<role>` with the role of the container (either `ps0`, `worker0`, or `worker1`). 

```shell
export ROLE=<role>
cd /luks_tools
./unmount_encrypted_vfs.sh ${ROLE}
```

### Transfer Encrypted Model Files to Trusted Node
Transfer the LUKS encrypted partition (`/root/vfs`) of the ps0 and worker0 containers to a trusted node. (The VM's `/home` directory is mounted to each container at `/home/host-home` to facilitate the file transfer for demonstration purposes.)

From the trusted node, as the root user, decrypt the encrypted storage. Replace `<path to vfs file>` with the path to the vfs file.

```shell
export VIRTUAL_FS=<path to vfs file>
export LOOP_DEVICE=$(losetup -f)
losetup ${LOOP_DEVICE} ${VIRTUAL_FS}
cryptsetup luksOpen ${LOOP_DEVICE} model
mkdir -p /root/model
mount /dev/mapper/model /root/model
```

The decrypted model files can now be obtained on the trusted node:

```shell
ls -l /root/model
```

When done examining the model files, unmount the partition:

```shell
umount /root/model
cryptsetup luksClose /dev/mapper/model
```

---
## Cloud Deployment

### 1. Aliyun ECS

[Aliyun ECS](https://help.aliyun.com/product/25365.html) (Elastic Compute Service) is
an IaaS (Infrastructure as a Service) level cloud computing service provided by Alibaba
Cloud. It builds eighth generation security-enhanced instance families based on Intel® TDX technology to provide a trusted and confidential environment with a higher security level.

About how to build TDX confidential computing instance, please refer to the below links:

Chinese version: https://www.alibabacloud.com/help/zh/elastic-compute-service/latest/build-a-tdx-confidential-computing-environment

English version：https://www.alibabacloud.com/help/en/elastic-compute-service/latest/build-a-tdx-confidential-computing-environment

***Notice:*** Ali TDX instance is under external public preview.

### 2. Microsoft Azure

Microsoft Azure [DCesv5-series](https://azure.microsoft.com/en-us/updates/confidential-vms-with-intel-tdx-dcesv5-ecesv5/) instances support Intel® TDX confidential computing technology.

The following is the configuration of the DCesv5-series instance used:

- Instance Type  : Standard_DC16es_v5
- Instance Kernel: 6.2.0-1016-azure
- Instance OS    : Ubuntu 22.04 LTS Gen 2 TDX

***Notice:*** Azure DCesv5-series instances were used under private preview.
