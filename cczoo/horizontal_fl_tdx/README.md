# Horizontal Federated Learning with Intel TDX

This solution presents a framework for developing a PPML(Privacy-Preserving Machine Learning) solution based on TensorFlow - Horizontal Federated Learning with Intel TDX.

## Introduction

How to ensure the privacy of participants in the distributed training process of deep neural networks is a current hot topic. Federated learning can solve the problem to a certain extent. In horizontal federated learning, each participant uses its own local data for algorithm iteration and only uploads gradient information instead of raw data, which guarantees data privacy to a large extent.

The commonly used encryption method in federated learning is Homomorphic Encryption(HE). In addition to HE, trusted execution environment (TEE) technology uses plaintext for calculation and uses a trusted computing base to ensure security. Intel TDX technology is a concrete realization of TEE technology. In this horizontal federated learning solution, we adopted a privacy protection computing solution based on Intel TDX technology.

This solution mainly include the following three aspects: 
-	RA-TLS enhanced gRPC - The RA-TLS technology is integrated in the gRPC framework to ensure the security of data transmission and enable remote verification technology.
-	Federated training – Propose a federated training solution based on Intel TDX and RA-TLS technology.
-	Model Protection – Using LUKS to protect model confidentiality and integrity during model training and model transfer. 

## Privacy protection
In this solution, privacy protection is provided in the following aspects:

### Runtime security using Intel TDX
Intel TDX technology offers hardware-based memory encryption that isolates specific application code and data in memory. Intel TDX allows user-level code to allocate private regions of memory based on a TD (Trust Domain) environment.

Intel TDX also helps protect against SW attacks even if OS/drivers/BIOS/VMM/SMM are compromised and helps increase protections for secrets even when attacker has full control of platform.

In the training phase of federated learning, the gradient information is stored inside the TD. Intel TDX provides assurance that no unauthorized access or memory snooping of the TD occurs to prevent leakage of gradient and model information.

### Encrypted transmission and remote attestation
We use the Remote Attestation with Transport Layer Security (RA-TLS) of Intel TDX technology to ensure security during transmission. This technology combines TLS technology and remote attestation technology. RA-TLS uses TEE as the hardware root of trust. The certificate and private key are generated in the TD and are not stored on the disk. Therefore, participants cannot obtain the certificate and private key in plain text, preventing the man-in-the-middle attacks. In this federated learning solution, RA-TLS is used to ensure the encrypted transmission of gradient information.

For more information about RA-TLS, please refer to the relevant [documentation](https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html)and [code](https://github.com/intel/confidential-computing-zoo/tree/main/cczoo/grpc-ra-tls).

### Model at-rest security 
We use the LUKS storage service to encrypt the model generated during the training process, to protect the model from being acquired by malicious hosts and only visible in the TD. Therefore, safe storage of the model is achieved. In addition, we use the Trusted machine with LUKS Secrets to obtain the model in TD through RA-TLS technology. Therefore, the safe migration of the model is achieved.

## Workflow
In the training process, each worker uses local data in its TD to complete a round of training, and then sends the gradient information in the backpropagation process to the parameter server through the RA-TLS technology, and then the parameter server completes the gradient aggregation and update network parameters, and then send the updated parameters to each worker. The workflow is as follows:

<div align=center>
<img src=../../documents/readthedoc/docs/source/Solutions/tdx-hfl/images/tdx_hfl.svg>
</div>

The training phase can be divided into the following steps:

&emsp;&ensp;**①** Using Intel TDX technology, the training program of the participants runs in different TDs. Create encrypted model directory on LUKS storage system and prepare LUKS decryption service.

&emsp;&ensp;**②** Workers calculate gradient information based on local data in the TD.

&emsp;&ensp;**③** Workers send gradient to parameter server through RA-TLS enhanced gRPC.

&emsp;&ensp;**④** Parameter server performs gradient aggregation and updates global model parameters.

&emsp;&ensp;**⑤** Parameter server sends model parameters to workers.

&emsp;&ensp;**⑥** Workers update local model parameters.

&emsp;&ensp;**⑦** Repeat steps **②**-**⑥** until the end of training. Finally, the training model directory is transmitted to the remote trusted node and finally decrypted.

## Horizontal federated training execution
We provide an image classification training task and it uses the cifar-10 dataset to train the ResNet network.

### Requirements

- Intel TDX software stack
- Docker

### Configuration

- framework: TensorFlow 2.6.0
- model: ResNet-50
- dataset: Cifar-10
- ps num: 1
- worker num: 2
- container num: 3

### Download source code
In TDVM, download the code used in this practice:
```shell
git clone https://github.com/intel/confidential-computing-zoo.git
cd confidential-computing-zoo/cczoo/horizontal_fl_tdx/
```

### Build Docker image
```shell
./build_docker_image.sh
```

### Start Docker container

Start three containers (ps0, worker0, worker1).

```shell
./start_container.sh <ps0/worker0/worker1>
```
***Notice:*** 
If you are using non-production version Intel CPU, please replace the `/usr/lib64/libsgx_dcap_quoteverify.so` file with non-production version.

### Configure node network address
If running in the cloud, please modify the `PCCS server address` in the `sgx_default_qcnl.conf` file and fill in the PCCS address of the cloud and ignore the `<PCCS ip addr>` parameter.

In the case of deploying different distributed nodes on multiple VMs, you can configure the distributed node IP address by modifying the `train.py` training script in the `/hfl-tensorflow` directory in the Docker container:

```shell
tf.app.flags.DEFINE_string("ps_hosts", "['localhost:60002']", "ps hosts")
tf.app.flags.DEFINE_string("worker_hosts", "['localhost:61002','localhost:61003']", "worker hosts")
```

***Notice:***

1. You need to modify the `localhost` fields in the above code segment to the IP address of the VMs where the training script is actually deployed.
2. Make sure that the port number configured on the current node has been enabled on the corresponding VM.

### Create encrypted directories
In the Docker environment of each computing node, an encrypted directory needs to be created to store model files to ensure the security of the model files.

Execute the following commands in each of the three Docker environments:

create luks block file and bind it to a idle loop device:

```shell
cd /luks_tools
VIRTUAL_FS=/root/vfs
./create_encrypted_vfs.sh ${VIRTUAL_FS}
```

According to the loop device number (such as `\dev\loop0`) output by the above command, create the LOOP_DEVICE environment variable to bind the loop device:

```shell
export LOOP_DEVICE=<the binded loop device>
```

The block loop device needs to be formatted to ext4 for the first execution.

```shell
./mount_encrypted_vfs.sh ${LOOP_DEVICE} format
```

Mount by password:

```shell
./unmount_encrypted_vfs.sh ${VIRTUAL_FS}
./mount_encrypted_vfs.sh ${LOOP_DEVICE} notformat
```

### Run the training scripts
Run the script for the corresponding job in each Docker container.

Docker container 1:

```shell
cd /hfl-tensorflow
./test-tdx.sh ps0
```

Docker container 2:

```shell
cd /hfl-tensorflow
./test-tdx.sh worker0
```

Docker container 3:

```shell
cd /hfl-tensorflow
./test-tdx.sh worker1
```

You can see the training log information from the workers' terminals to confirm that the training is running normally.

At the beginning of training, two-by-two remote verification between nodes will be performed. Only after the remote verification is passed can the training continue. After successful remote attestation, the terminal will output the following:

```shell
Info: tdx_qv_get_quote_supplemental_data_size successfully returned.
Info: App: tdx_qv_verify_quote successfully returned.
Info: App: Verification completed successfully.
```

The model files generated during training will be saved in the `model` folder. In this example, the information related to variable values is stored in `model/model.ckpt-data` of `ps0`, and the information related to the computational graph structure is stored in `model/model.ckpt-meta` of `worker0`.

Unmount after training is complete:

```shell
cd /luks_tools
./unmount_encrypted_vfs.sh ${VIRTUAL_FS}
```

### Get model files on trusted node
After transferring the LUKS encrypted partition (`/root/vfs`) to the customer's trusted environment, decrypt it in the trusted node and obtain the model file.

If the path of the encrypted partition in the trusted node is `/root/vfs`, the command to decrypt and obtain the model file is as follows:

```shell
VIRTUAL_FS=/root/vfs
export LOOP_DEVICE=$(losetup -f)
losetup ${LOOP_DEVICE} ${VIRTUAL_FS}
cryptsetup luksOpen ${LOOP_DEVICE} model
mkdir /root/model
mount /dev/mapper/model /root/model
```

Finally, the decrypted model file is obtained on the trusted node:

```shell
ls /root/model
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
