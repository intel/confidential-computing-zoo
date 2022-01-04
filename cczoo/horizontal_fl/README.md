# Horizontal Federated Learning with Intel SGX Solution

This solution presents a framework for developing a PPML(Privacy-Preserving Machine Learning) solution based on TensorFlow - Horizontal Federated Learning with Intel SGX.

## Introduction

How to ensure the privacy of participants in the distributed training process of deep neural networks is a current hot topic. Federated learning can solve the problem to a certain extent. In horizontal federated learning, each participant uses its own local data for algorithm iteration and only uploads gradient information instead of raw data, which guarantees data privacy to a large extent. 

The commonly used encryption method in federated learning is Homomorphic Encryption(HE). In addition to HE, trusted execution environment (TEE) technology uses plaintext for calculation and uses a trusted computing base to ensure security. Intel SGX technology is a concrete realization of TEE technology. In this horizontal federated learning solution, we adopted a privacy protection computing solution based on Intel SGX technology.

### Encrypted runtime environment
 Intel SGX technology offers hardware-based memory encryption that isolates specific application code and data in memory. Intel SGX allows user-level code to allocate private regions of memory, called enclaves, which are designed to be protected from processes running at higher privilege levels.

Intel SGX also helps protect against SW attacks even if OS/drivers/BIOS/VMM/SMM are compromised and helps increase protections for secrets even when attacker has full control of platform.

### Encrypted transmission and remote attestation
In the communication part of horizontal federated learning, we use Intel SGX Remote Attestation with Transport Layer Security (RA-TLS) technology to perform encrypted transmission and verification of program integrity.[<sup>[1]</sup>](#refer-anchor-1) RA-TLS integrates Intel SGX remote attestation with the establishment of a standard Transport Layer Security (TLS) connection. Remote attestation is performed during the connection setup by embedding the attestation evidence into the endpoints TLS certificate.

## Privacy protection
This solution mainly contains the items listed below: 
-	AI Framework – TensorFlow, an open-source platform for machine learning. 
-	Security Isolation LibOS – Gramine, an open-source project for Intel SGX, can run applications with no modification in Intel SGX. 
-	Platform Integrity - Providing Remote Attestation mechanism, so that user can gain trust in the remote Intel SGX platform.

In this solution, privacy protection is provided in the following aspects:
### Runtime security using Intel-SGX
In the training phase of federated learning, the gradient information is stored inside the Intel SGX enclave. Intel SGX provides some assurance that no unauthorized access or memory snooping of the enclave occurs to prevent any leakage of gradient and model related information.
### In-Transit security
We use the Remote Attestation with Transport Layer Security (RA-TLS) of Intel SGX technology to ensure security during transmission. This technology is proposed by Intel's security team, which combines TLS technology and remote attestation technology. RA-TLS uses TEE as the hardware root of trust. The certificate and private key are generated in the enclave and are not stored on the disk. Therefore, it is impossible for the participants to obtain the certificate and private key in plain text, so man-in-the-middle attacks cannot be carried out. In this federated learning solution, RA-TLS is used to ensure the encrypted transmission of gradient information.
### Application integrity
To solve the problem of how to verify the untrusted application integrity, we use RA-TLS to verify the Intel SGX enclave. It ensures that the runtime application is a trusted version.

## Workflow
In the training process, each worker uses local data in its enclave to complete a round of training, and then sends the gradient information in the backpropagation process to the parameter server through the RA-TLS technology, and then the parameter server completes the gradient aggregation and update network parameters, and then send the updated parameters to each worker. The workflow is as follows:

<div align=center>
<img src=../../documents/readthedoc/docs/source/Solutions/horizontal-federated-learning/images/HFL.svg>
</div>

The training phase can be divided into the following steps:

&emsp;&ensp;**①** Using Intel SGX technology, the training program of the participants runs in different enclaves.

&emsp;&ensp;**②** Workers calculate gradient information based on local data in the enclave environment.

&emsp;&ensp;**③** Workers send gradient to parameter server through RA-TLS.

&emsp;&ensp;**④** Parameter server performs gradient aggregation and updates global model parameters in the enclave.

&emsp;&ensp;**⑤** Parameter server sends model parameters to workers.

&emsp;&ensp;**⑥** Workers update local model parameters.

Steps **②**-**⑥** will be repeated continuously during the training process. Since the workers and the parameter server run in memory-encrypted enclave environment, and RA-TLS technology guarantees encryption during transmission, this solution can ensure privacy during training.

## Horizontal federated training execution

### Requirements

- a machine that supports Intel SGX and FLC/DCAP
- EPC size: 64GB
- Docker

### Configuration

- framework: TensorFlow 2.4.2
- model: ResNet-50
- dataset: Cifar-10
- ps num: 2
- worker num: 2

### Build Docker image

```shell
./build_docker_image.sh
```

### Start container
```shell
./start_container.sh <attestation ip addr>
```

### Start aesm service
```shell
/start_aesm_service.sh
```

### Run the training scripts
```shell
cd hfl-tensorflow
test-sgx.sh make
test-sgx.sh ps0
test-sgx.sh ps1
test-sgx.sh worker0
test-sgx.sh worker1
```

<div id="refer-anchor-1"></div>

- [1] [Knauth, Thomas, et al. "Integrating remote attestation with transport layer security." arXiv preprint arXiv:1801.05863 (2018).](https://arxiv.org/pdf/1801.05863)
