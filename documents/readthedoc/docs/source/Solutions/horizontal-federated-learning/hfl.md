# Horizontal Federated Learning with Intel SGX Solution

This solution presents a framework for developing a PPML (Privacy-Preserving Machine Learning) solution based on TensorFlow - Horizontal Federated Learning with Intel SGX.

## Introduction

How to ensure the privacy of participants in the distributed training process of deep neural networks is a current hot topic. Federated learning can solve the problem to a certain extent. In horizontal federated learning, each participant uses its own local data for algorithm iteration and only uploads gradient information instead of raw data, which guarantees data privacy to a large extent. 

The commonly used encryption method in federated learning is Homomorphic Encryption (HE). In addition to HE, trusted execution environment (TEE) technology uses plaintext for calculation and uses a trusted computing base to ensure security. Intel SGX technology is a concrete realization of TEE technology. In this horizontal federated learning solution, we adopted a privacy protection computing solution based on Intel SGX technology.

### Encrypted Runtime Environment
Intel SGX technology offers hardware-based memory encryption that isolates specific application code and data in memory. Intel SGX allows user-level code to allocate private regions of memory, called enclaves, which are designed to be protected from processes running at higher privilege levels.

Intel SGX also helps protect against SW attacks even if OS/drivers/BIOS/VMM/SMM are compromised and helps increase protections for secrets even when attacker has full control of platform.

### Encrypted Transmission and Remote Attestation
In the communication part of horizontal federated learning, we use Intel SGX Remote Attestation with Transport Layer Security (RA-TLS) technology to perform encrypted transmission and verification of program integrity.[<sup>[1]</sup>](https://arxiv.org/ftp/arxiv/papers/1801/1801.05863.pdf) RA-TLS integrates Intel SGX remote attestation with the establishment of a standard Transport Layer Security (TLS) connection. Remote attestation is performed during the connection setup by embedding the attestation evidence into the endpoints TLS certificate.

## Privacy Protection
This solution contains the items listed below: 
-	AI Framework – TensorFlow, an open-source platform for machine learning. 
-	Security Isolation LibOS – Gramine, an open-source project for Intel SGX, can run applications with no modification in Intel SGX. 
-	Platform Integrity - Providing Remote Attestation mechanism, so that user can gain trust in the remote Intel SGX platform.

In this solution, privacy protection is provided in the following aspects:
### Runtime Security Using Intel SGX
In the training phase of federated learning, the gradient information is stored inside the Intel SGX enclave. Intel SGX provides some assurance that no unauthorized access or memory snooping of the enclave occurs to prevent any leakage of gradient and model related information.
### In-Transit Security
We use the Remote Attestation with Transport Layer Security (RA-TLS) of Intel SGX technology to ensure security during transmission. This technology is proposed by Intel's security team, which combines TLS technology and remote attestation technology. RA-TLS uses TEE as the hardware root of trust. The certificate and private key are generated in the enclave and are not stored on the disk. Therefore, it is impossible for the participants to obtain the certificate and private key in plain text, so man-in-the-middle attacks cannot be carried out. In this federated learning solution, RA-TLS is used to ensure the encrypted transmission of gradient information.
### Application Integrity
To solve the problem of how to verify the untrusted application integrity, we use RA-TLS to verify the Intel SGX enclave. It ensures that the runtime application is a trusted version.

## Workflow
In the training process, each worker uses local data in its enclave to complete a round of training, and then sends the gradient information in the backpropagation process to the parameter server through the RA-TLS technology, and then the parameter server completes the gradient aggregation and update network parameters, and then send the updated parameters to each worker. The workflow is as follows:

![](images/HFL.svg)

The training phase can be divided into the following steps:

&emsp;&ensp;**①** Using Intel SGX technology, the training program of the participants runs in different enclaves.

&emsp;&ensp;**②** Workers calculate gradient information based on local data in the enclave environment.

&emsp;&ensp;**③** Workers send gradient to parameter server through RA-TLS.

&emsp;&ensp;**④** Parameter server performs gradient aggregation and updates global model parameters in the enclave.

&emsp;&ensp;**⑤** Parameter server sends model parameters to workers.

&emsp;&ensp;**⑥** Workers update local model parameters.

Steps **②**-**⑥** will be repeated continuously during the training process. Since the workers and the parameter server run in memory-encrypted enclave environment, and RA-TLS technology guarantees encryption during transmission, this solution can ensure privacy during training.

## Solution Ingredients
This solution leverages the following ingredients.
- [TensorFlow](https://www.tensorflow.org/)
- [Gramine](https://gramine.readthedocs.io)

## Prerequisites

- Ubuntu 20.04. This solution should work on other Linux distributions as well, but for simplicity we provide the steps for Ubuntu 20.04.

- Docker Engine. Docker Engine is an open-source containerization technology for building and containerizing your applications. In this tutorial, applications like Gramine and TensorFlow will be built into Docker container images. Please follow this [guide](https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script) to install Docker engine. It is recommended to use a data disk of at least 128GB for the docker daemon data directory. This [guide](https://docs.docker.com/config/daemon/#daemon-data-directory) describes how to configure the docker daemon data directory. If behind a proxy server, please refer to this [guide]( https://docs.docker.com/config/daemon/systemd/) for configuring the docker daemon proxy settings.

- CCZoo source:

```shell
   git clone https://github.com/intel/confidential-computing-zoo.git
```

- System with processor that supports Intel® Software Guard Extensions (Intel® SGX), Datacenter Attestation Primitives (DCAP), and Flexible Launch Control (FLC).

- If using Microsoft Azure, run the following script to install general dependencies, Intel SGX DCAP dependencies, and the Azure DCAP Client. To run this script:

```shell
   cd <cczoo_base_dir>/cczoo/horizontal_fl
   sudo ./setup_azure_vm.sh
```
  Verify the Intel Architectural Enclave Service Manager is active (running):

```shell  
   sudo systemctl status aesmd
```
  
- EPC size: 64GB for image classification solution, 256GB for recommendation system solution


## Recommendation System
### Configuration

- Model: dlrm
- Dataset: click-through record in Kaggle Cretio Ad dataset
- Number of containers for ps: 1
- Number of containers for workers: 4
- CPU cores: 45
- EPC size: 256GB

### Download Dataset

Download the [dataset](https://docs.google.com/uc?export=download&id=1xkmlOTtgqSQEWEi7ieHWYvlAl5bSthSr) to the `<cczoo_base_dir>/cczoo/horizontal_fl/recommendation_system/dataset` directory:

```shell
cd <cczoo_base_dir>/cczoo/horizontal_fl/recommendation_system/dataset
wget --load-cookies /tmp/cookies.txt "https://docs.google.com/uc?export=download&confirm=$(wget --quiet --save-cookies /tmp/cookies.txt --keep-session-cookies --no-check-certificate 'https://docs.google.com/uc?export=download&id=1xkmlOTtgqSQEWEi7ieHWYvlAl5bSthSr' -O- | sed -rn 's/.*confirm=([0-9A-Za-z_]+).*/\1\n/p')&id=1xkmlOTtgqSQEWEi7ieHWYvlAl5bSthSr" -O train.tar && rm -rf /tmp/cookies.txt
```

Alternatively, the dataset can be obtained from [BaiduNetdisk](https://pan.baidu.com/s/1BkMBDMghvJXp0wK9EQHtMg?pwd=c7cf).

### Build Container Image
```shell
cd <cczoo_base_dir>/cczoo/horizontal_fl
```
To build the container image for use on Microsoft Azure:
```shell
./build_docker_image.sh recommendation_system azure
```
To build the container image based on Anolis OS:
```shell
./build_docker_image.sh recommendation_system anolisos
```
To build the default container image:
```shell
./build_docker_image.sh recommendation_system default
```
NOTE: To specify the proxy server, set the `proxy_server` variable prior to the call to `build_docker_image.sh`, for example:
```shell
proxy_server=http://proxyserver:port ./build_docker_image.sh recommendation_system azure
```
   
### Start Containers and Run Training Scripts
Start five containers (ps0, worker0, worker1, worker2, worker3) and run the script for the corresponding job in each container.
`<IMAGEID>` is the image ID of the container built in the previous section.

#### For Use on Microsoft Azure:

```shell
./start_container.sh ps0 <IMAGEID>
docker exec -it ps0 bash
cd /recommendation_system
test-sgx.sh ps0
```
```shell
./start_container.sh worker0 <IMAGEID>
docker exec -it worker0 bash
cd /recommendation_system
test-sgx.sh worker0
```
```shell
./start_container.sh worker1 <IMAGEID>
docker exec -it worker1 bash
cd /recommendation_system
test-sgx.sh worker1
```
```shell
./start_container.sh worker2 <IMAGEID>
docker exec -it worker2 bash
cd /recommendation_system
test-sgx.sh worker2
```
```shell
./start_container.sh worker3 <IMAGEID>
docker exec -it worker3 bash
cd /recommendation_system
test-sgx.sh worker3
```

#### For Anolis OS and Other Cloud Deployments:

If running locally in a non-cloud environment, use the local PCCS server address for the `<PCCS ip addr>` parameter. If running in a cloud environment,  use `127.0.0.1` for the `<PCCS ip addr>` parameter, and then modify the `PCCS server address` value in `/etc/sgx_default_qcnl.conf`. `<IMAGEID>` is the image ID of the container built in the previous section.

```shell
./start_container.sh ps0 <IMAGEID> <PCCS ip addr>
cd /recommendation_system
test-sgx.sh ps0
```
```shell
./start_container.sh worker0 <IMAGEID> <PCCS ip addr>
cd /recommendation_system
test-sgx.sh worker0
```
```shell
./start_container.sh worker1 <IMAGEID> <PCCS ip addr>
cd /recommendation_system
test-sgx.sh worker1
```
```shell
./start_container.sh worker2 <IMAGEID> <PCCS ip addr>
cd /recommendation_system
test-sgx.sh worker2
```
```shell
./start_container.sh worker3 <IMAGEID> <PCCS ip addr>
cd /recommendation_system
test-sgx.sh worker3
```

#### Expected Results:
Monitor the training log on each worker container (`/recommendation_system/worker*.log`) until the training has completed. Training is completed when the training log contains `DLRM training finished.`. The ps0 container saves the variable values in the `/recommendation_system/model` directory. The worker0 container saves the computational graph structure in the `/recommendation_system/model` directory.

## Image Classification

### Configuration

- Model: ResNet-50
- Dataset: Cifar-10
- Number of containers for ps: 1
- Number of containers for workers: 2
- CPU cores: 6
- EPC size: 64GB

### Build Container Image
```shell
cd <cczoo_base_dir>/cczoo/horizontal_fl
```
To build the container image for use on Microsoft Azure:
```shell
./build_docker_image.sh image_classification azure
```
To build the container image based on Anolis OS:
```shell
./build_docker_image.sh image_classification anolisos
```
To build the default container image:
```shell
./build_docker_image.sh image_classification default
```
NOTE: To specify the proxy server, set the `proxy_server` variable prior to the call to `build_docker_image.sh`, for example:
```shell
proxy_server=http://proxyserver:port ./build_docker_image.sh image_classification azure
```

### Start Containers and Run Training Scripts
Start three containers (ps0, worker0, worker1) and run the script for the corresponding job in each container.
`<IMAGEID>` is the image ID of the container built in the previous section.

#### For Use on Microsoft Azure:

```shell
./start_container.sh ps0 <IMAGEID>
docker exec -it ps0 bash
cd /image_classification
test-sgx.sh ps0
```
```shell
./start_container.sh worker0 <IMAGEID>
docker exec -it worker0 bash
cd /image_classification
test-sgx.sh worker0
```
```shell
./start_container.sh worker1 <IMAGEID>
docker exec -it worker1 bash
cd /image_classification
test-sgx.sh worker1
```

#### For Anolis OS and Other Cloud Deployments:

If running locally in a non-cloud environment, use the local PCCS server address for the `<PCCS ip addr>` parameter. If running in a cloud environment,  use `127.0.0.1` for the `<PCCS ip addr>` parameter, and then modify the `PCCS server address` value in `/etc/sgx_default_qcnl.conf`. `<IMAGEID>` is the image ID of the container built in the previous section.

```shell
./start_container.sh ps0 <IMAGEID> <PCCS ip addr>
cd /image_classification
test-sgx.sh ps0
```
```shell
./start_container.sh worker0 <IMAGEID> <PCCS ip addr>
cd /image_classification
test-sgx.sh worker0
```
```shell
./start_container.sh worker1 <IMAGEID> <PCCS ip addr>
cd /image_classification
test-sgx.sh worker1
```

#### Expected Results:

Monitor the training log on each worker container (`/image_classification/worker*-gramine-python.log`) until the training has completed. Training is completed when the training log contains `Optimization finished.`. The ps0 container saves the variable values in the `/image_classification/model` directory. The worker0 container saves the computational graph structure in the `/image_classification/model` directory.


---
## Cloud Deployment

### 1. Aliyun ECS

[Aliyun ECS](https://help.aliyun.com/product/25365.html) (Elastic Compute Service) is
an IaaS (Infrastructure as a Service) level cloud computing service provided by Alibaba
Cloud. It builds security-enhanced instance families [g7t, c7t, r7t](https://help.aliyun.com/document_detail/207734.html)
based on Intel® SGX technology to provide a trusted and confidential environment
with a higher security level.

The configuration of the ECS instance as below:

- Instance Type  : [g7t](https://help.aliyun.com/document_detail/108490.htm#section-bew-6jv-c0k).
- Instance Kernel: 4.19.91-24
- Instance OS    : Alibaba Cloud Linux 2.1903
- Instance Encrypted Memory: 32G
- Instance vCPU  : 16
- Instance SGX PCCS Server Addr: [sgx-dcap-server.cn-hangzhou.aliyuncs.com](https://help.aliyun.com/document_detail/208095.html)

***Notice***: Please replace server link in `sgx_default_qcnl.conf` included in the dockerfile with Aliyun PCCS server address.

### 2. Tencent Cloud

Tencent Cloud Virtual Machine (CVM) provide one instance named [M6ce](https://cloud.tencent.com/document/product/213/11518#M6ce),
which supports Intel® SGX encrypted computing technology.

The configuration of the M6ce instance as below:

- Instance Type  : [M6ce.4XLARGE128](https://cloud.tencent.com/document/product/213/11518#M6ce)
- Instance Kernel: 5.4.119-19-0009.1
- Instance OS    : TencentOS Server 3.1
- Instance Encrypted Memory: 64G
- Instance vCPU  : 16
- Instance SGX PCCS Server: [sgx-dcap-server-tc.sh.tencent.cn](https://cloud.tencent.com/document/product/213/63353)

***Notice***: Please replace server link in `sgx_default_qcnl.conf` included in the dockerfile with Tencent PCCS server address.

### 3. ByteDance Cloud

ByteDance Cloud (Volcengine SGX Instances) provides the instance named `ebmg2t`,
which supports Intel® SGX encrypted computing technology.

The configuration of the ebmg2t instance as below:

- Instance Type  : `ecs.ebmg2t.32xlarge`.
- Instance Kernel: kernel-5.15
- Instance OS    : ubuntu-20.04
- Instance Encrypted Memory: 256G
- Instance vCPU  : 16
- Instance SGX PCCS Server: `sgx-dcap-server.bytedance.com`.

### 4. Microsoft Azure

Microsoft Azure [DCsv3-series](https://docs.microsoft.com/en-us/azure/virtual-machines/dcv3-series) instances support Intel® SGX encrypted computing technology.

DCsv3-series instance used for the recommendation system solution:

- Instance Type  : Standard_DC48s_v3
- Instance Kernel: 5.15.0-1014-azure
- Instance OS    : Ubuntu Server 20.04 LTS - Gen2
- Instance Encrypted Memory: 256G
- Instance vCPU  : 48

DCsv3-series instance used for the image classification solution:

- Instance Type  : Standard_DC16s_v3
- Instance Kernel: 5.15.0-1014-azure
- Instance OS    : Ubuntu Server 20.04 LTS - Gen2
- Instance Encrypted Memory: 64G
- Instance vCPU  : 16

[1] [Knauth, Thomas, et al. "Integrating remote attestation with transport layer security." arXiv preprint arXiv:1801.05863 (2018).](https://arxiv.org/pdf/1801.05863)
