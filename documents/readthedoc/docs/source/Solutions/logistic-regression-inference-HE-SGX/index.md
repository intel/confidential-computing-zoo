# Secure Logistic Regression Inference with HE and Intel SGX
## Introduction
Nowadays, a wide variety of applications are available as SaaS applications. More and more AI workloads are deployed to the cloud. 
AI model providers benefit from the powerful data computing capability of the cloud and reduce the difficulty of maintaining a complex AI inference service. 
However, most of AI models are treated as the intellectual properties of AI model provider. 
How to protect AI models from disclosing to other parties including CSP is a problem that we need to address.  
On the other hand, users want to obtain precise inference result by utilizing the AI model which is trained from massive data. 
However, they don’t want to reveal their privacy data for the inference. Although, they can do AI inference locally by downloading the AI model to their end devices. 
But it is not feasible when the AI workload is very heavy, because the computing capability of most end devices, such as smart phones, are limited. 
Moreover, model providers don’t intend to share their AI models to end users directly either.

## Solution Description
To address the above two problems, we developed a solution of secure AI inference based on SGX and HE. In this solution, we assume the AI workload executes on an enclave of cloud server with SGX enabled. 
To convince the model provider to believe their AI workloads are not tampered and run in an enclave, the cloud server generates quote and sends to model provider for remote attestation. 
After passing the quote verification, the model provider deploys the AI workload to the cloud and launch the AI inference service.  
The user generates a HE key pair locally and encrypts privacy data for inference with the public key. The encrypted data is transferred to the cloud server and do inference there. 
After the inference is completed, the encrypted result is sent back to the user through gRPC. User decrypts it with the private key and obtains the plaintext of finial result.

![image](https://user-images.githubusercontent.com/27326867/197438740-9923ca2e-0911-40a0-bf5e-d0bcebc78609.png)

## Build and Run
### Prerequisite
- A server with Intel SGX enabled
- Docker Engine. Docker Engine is an open source containerization technology for
  building and containerizing your applications.
  Please follow [this guide](https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script)
  to install Docker engine.
### Build Docker Image
```
git clone https://github.com/intel/confidential-computing-zoo
cd confidential-computing-zoo/cczoo/lr_infer_he_sgx
```
For deployments on Microsoft Azure:
```shell
AZURE=1 ./build_docker_image.sh
```
For Anolis OS cloud deployments:
```shell
./build_docker_image.sh anolisos
```
### Execution
Open 2 terminals, one for the inference client that has data to be inferred and the other for the inference server that has a AI model.
- Inference server
```
./start_container.sh server [ubuntu/anolisos]
```
- Inference client
```
./start_container.sh client [ubuntu/anolisos]
```
### Result
>EncryptionParameters: wrote 91 bytes  
PublicKey: wrote 709085 bytes  
RelinKeys: wrote 3545129 bytes  
HE inference result - accuracy: 0.944  


## Acknowledgement
Thanks [Intel HE Toolkit](https://github.com/intel/he-toolkit) project for contributing the code base of [logistic regression example](https://github.com/intel/he-toolkit/tree/main/he-samples/examples/logistic-regression).

## Reference
Intel HE Toolkit: https://github.com/intel/he-toolkit  
Intel SGX: https://www.intel.com/content/www/us/en/developer/tools/software-guard-extensions/overview.html
